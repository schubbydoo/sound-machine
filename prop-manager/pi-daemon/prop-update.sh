#!/bin/bash
set -e

INSTALL_DIR=/opt/propmanager
SOURCE_PATH_FILE="$INSTALL_DIR/.source_path"

# ── Must run as root ────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root:  sudo bash prop-update.sh"
    exit 1
fi

# ── Find repo ───────────────────────────────────────────────────
if [[ ! -f "$SOURCE_PATH_FILE" ]]; then
    echo "Error: source path not found. Run install.sh first."
    exit 1
fi
DAEMON_SRC=$(cat "$SOURCE_PATH_FILE")
REPO=$(git -C "$DAEMON_SRC" rev-parse --show-toplevel 2>/dev/null || echo "")

if [[ -z "$REPO" ]]; then
    echo "Error: $DAEMON_SRC is not inside a git repo."
    exit 1
fi

# Pull as the repo owner (not root — root may lack the SSH key)
REPO_OWNER=$(stat -c '%U' "$REPO")
echo "==> Pulling latest from GitHub (as $REPO_OWNER)..."
sudo -u "$REPO_OWNER" git -C "$REPO" pull

echo "==> Deploying daemon files..."
cp "$DAEMON_SRC/daemon.py"        "$INSTALL_DIR/daemon.py"
cp "$DAEMON_SRC/wifi.py"          "$INSTALL_DIR/wifi.py"
cp "$DAEMON_SRC/requirements.txt" "$INSTALL_DIR/requirements.txt"

echo "==> Updating Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

echo "==> Restarting propmanager..."
systemctl restart propmanager

echo ""
systemctl status propmanager --no-pager -l
