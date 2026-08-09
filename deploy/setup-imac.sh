#!/usr/bin/env bash
# One-time setup for the iMac that will run GridIron.
# Idempotent: safe to re-run after a failed step or to pick up changes.
#
# Usage:
#   ./deploy/setup-imac.sh
#   REPO_URL=git@github.com:me/ff-dashboard.git APP_DIR=~/gridiron ./deploy/setup-imac.sh
#
# This script is meant to be copied/cloned onto the iMac and run there
# directly (it is also the first thing a fresh clone gives you).

set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:CHANGEME/ff-dashboard.git}"
APP_DIR="${APP_DIR:-$HOME/gridiron}"
PLIST_LABEL="com.gridiron.app"
PLIST_SRC_NAME="com.gridiron.app.plist"

step() {
	echo
	echo "==> $*"
}

step "Checking for Homebrew"
if ! command -v brew >/dev/null 2>&1; then
	echo "Homebrew is required but was not found." >&2
	echo "Install it first: https://brew.sh" >&2
	echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' >&2
	exit 1
fi
echo "Homebrew found: $(command -v brew)"

step "Checking for uv"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
	echo "Installing uv via Homebrew..."
	brew install uv
else
	echo "uv already present"
fi

step "Checking for node"
if ! command -v node >/dev/null 2>&1; then
	echo "Installing node via Homebrew..."
	brew install node
else
	echo "node already present: $(command -v node)"
fi

step "Checking for Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
	echo "The Tailscale CLI was not found." >&2
	echo "Install the Tailscale app first, then enable the CLI:" >&2
	echo "  https://tailscale.com/download/mac" >&2
	echo "(The tailscale binary is normally symlinked from the Tailscale.app bundle" >&2
	echo " via Tailscale menu bar icon -> Install Command Line Tool.)" >&2
	exit 1
fi
echo "Tailscale CLI found: $(command -v tailscale)"

step "Cloning repo (if needed)"
if [ ! -d "$APP_DIR" ]; then
	echo "Cloning $REPO_URL into $APP_DIR"
	git clone "$REPO_URL" "$APP_DIR"
else
	echo "$APP_DIR already exists, skipping clone"
fi

step "Installing backend dependencies (uv sync)"
(cd "$APP_DIR" && uv sync)

step "Building frontend"
(cd "$APP_DIR/frontend" && npm ci && npm run build)

step "Checking .env"
if [ ! -f "$APP_DIR/.env" ]; then
	cp "$APP_DIR/.env.example" "$APP_DIR/.env"
	echo "Created $APP_DIR/.env from .env.example."
	echo "Edit it now to fill in GRIDIRON_SECRET_KEY, Yahoo/ESPN credentials, etc."
	read -r -p "Press Enter once $APP_DIR/.env is filled in and saved to continue... " _
else
	echo "$APP_DIR/.env already exists, leaving it alone"
fi

step "Running database migrations"
(cd "$APP_DIR" && uv run alembic upgrade head)

step "Configuring power settings (requires sudo)"
sudo pmset -c sleep 0
sudo pmset autorestart 1
sudo pmset -c disksleep 0
echo "NOTE: pmset cannot enable these from the CLI — set them manually in"
echo "      System Settings:"
echo "        - Users & Groups -> enable automatic login for this user"
echo "        - Energy Saver / Battery -> 'Wake for network access'"

step "Publishing on the tailnet"
tailscale serve --bg 8000
echo "Tailscale serve status:"
tailscale serve status

step "Installing LaunchAgent"
mkdir -p "$HOME/Library/Logs/gridiron"
mkdir -p "$HOME/Library/LaunchAgents"

PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
sed \
	-e "s#__APP_DIR__#${APP_DIR}#g" \
	-e "s#__HOME__#${HOME}#g" \
	"$APP_DIR/deploy/${PLIST_SRC_NAME}" >"$PLIST_DEST"
echo "Wrote $PLIST_DEST"

if launchctl print "gui/$(id -u)/${PLIST_LABEL}" >/dev/null 2>&1; then
	echo "LaunchAgent already loaded, bootout before reloading"
	launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" || true
fi
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
echo "LaunchAgent bootstrapped"

step "Health check"
HEALTH_OK=0
if curl --fail --silent --show-error --retry 5 --retry-delay 2 --retry-connrefused \
	"http://127.0.0.1:8000/api/health" >/dev/null; then
	HEALTH_OK=1
fi

if [ "$HEALTH_OK" -eq 1 ]; then
	echo
	echo "GridIron is up: http://127.0.0.1:8000/api/health"
else
	echo
	echo "GridIron did NOT come up healthy." >&2
	echo "Check logs: $HOME/Library/Logs/gridiron/app.log / app.err.log" >&2
	exit 1
fi
