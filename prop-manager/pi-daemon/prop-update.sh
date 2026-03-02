#!/bin/bash
set -e

REPO=/opt/sound-machine
DAEMON_SRC=$REPO/prop-manager/pi-daemon

echo "==> Pulling latest from GitHub..."
git -C "$REPO" pull

echo "==> Deploying daemon files..."
cp "$DAEMON_SRC/daemon.py" /opt/propmanager/daemon.py
cp "$DAEMON_SRC/wifi.py"   /opt/propmanager/wifi.py

echo "==> Restarting propmanager..."
systemctl restart propmanager
systemctl status propmanager --no-pager -l
