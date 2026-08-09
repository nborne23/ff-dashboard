#!/usr/bin/env bash
# Runs ON the iMac, invoked by `make deploy` over ssh:
#   ssh $(IMAC_HOST) 'cd $(IMAC_DIR) && ./deploy/deploy.sh'
#
# Pulls the latest git HEAD, rebuilds, migrates, and restarts the
# LaunchAgent, then waits for the health endpoint to come back up.

set -euo pipefail

PLIST_LABEL="com.gridiron.app"
HEALTH_URL="http://127.0.0.1:8000/api/health"
LOG_DIR="$HOME/Library/Logs/gridiron"

step() {
	echo
	echo "==> $*"
}

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
