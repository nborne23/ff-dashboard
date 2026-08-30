#!/usr/bin/env bash
# Runs ON the iMac, invoked by `make deploy` over ssh:
#   ssh $(IMAC_HOST) 'cd $(IMAC_DIR) && ./deploy/deploy.sh'
#
# Pulls the latest git HEAD, rebuilds, migrates, and restarts the
# LaunchAgent, then waits for the health endpoint to come back up.

set -euo pipefail

# `ssh host 'cmd'` runs a NON-INTERACTIVE, NON-LOGIN shell, which under zsh reads only
# ~/.zshenv — not ~/.zshrc or ~/.zprofile, where uv's and Homebrew's PATH entries
# normally live. So `uv` and `npm` resolve fine when you ssh in and type them by hand,
# and both vanish when this script runs over ssh.
#
# The same normalization already appears twice in this repo: setup-imac.sh exports
# $HOME/.local/bin after installing uv, and com.gridiron.app.plist hardcodes the full
# PATH for launchd (which has the same problem for the same reason). This is the third
# place that needs it. Prepended rather than replaced, so nothing already on PATH is lost.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

PLIST_LABEL="com.gridiron.app"
HEALTH_URL="http://127.0.0.1:8000/api/health"
LOG_DIR="$HOME/Library/Logs/gridiron"

step() {
	echo
	echo "==> $*"
}

# Fail with a usable message rather than "command not found" three steps in.
step "Checking required tools"
MISSING=0
for tool in uv npm git; do
	if command -v "$tool" >/dev/null 2>&1; then
		echo "  $tool: $(command -v "$tool")"
	else
		echo "  $tool: NOT FOUND" >&2
		MISSING=1
	fi
done
if [ "$MISSING" -eq 1 ]; then
	echo >&2
	echo "A required tool is not on PATH for a non-interactive ssh session." >&2
	echo "PATH was: $PATH" >&2
	echo "Install it, or add its directory to the export at the top of this script." >&2
	exit 127
fi

step "Pulling latest code"
git pull --ff-only

step "Installing backend dependencies (uv sync)"
uv sync

step "Building frontend"
cd frontend
npm ci
npm run build
cd ..

step "Running database migrations"
uv run alembic upgrade head

step "Restarting LaunchAgent"
launchctl kickstart -k "gui/$(id -u)/${PLIST_LABEL}"

step "Waiting for health check"
ATTEMPTS=15
SLEEP_SECONDS=2
HEALTHY=0
for ((i = 1; i <= ATTEMPTS; i++)); do
	if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null 2>&1; then
		HEALTHY=1
		break
	fi
	sleep "$SLEEP_SECONDS"
done

if [ "$HEALTHY" -eq 1 ]; then
	echo
	echo "Deploy succeeded: $HEALTH_URL is healthy"
else
	echo
	echo "Deploy FAILED: $HEALTH_URL never became healthy after $((ATTEMPTS * SLEEP_SECONDS))s" >&2
	echo "Check logs: $LOG_DIR/app.log / app.err.log" >&2
	exit 1
fi
