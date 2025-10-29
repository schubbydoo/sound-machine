#!/bin/bash
# Setup systemd services for Sound Machine LED and Audio daemons

set -e

echo "=========================================="
echo "Sound Machine - Systemd Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

PROJECT_DIR="/home/soundconsole/sound-machine"

echo ""
echo "Step 1: Installing service files..."
echo "  - Copying sound-led-daemon.service"
cp "$PROJECT_DIR/systemd/sound-led-daemon.service" /etc/systemd/system/
echo "  - Copying soundtrigger.service"
cp "$PROJECT_DIR/systemd/soundtrigger.service" /etc/systemd/system/

echo ""
echo "Step 2: Reloading systemd daemon..."
systemctl daemon-reload

echo ""
echo "Step 3: Enabling services to start on boot..."
systemctl enable sound-led-daemon.service
systemctl enable soundtrigger.service

echo ""
echo "Step 4: Starting services now..."
systemctl start sound-led-daemon.service
sleep 1
systemctl start soundtrigger.service

echo ""
echo "Step 5: Verifying services..."
echo "  LED Daemon status:"
systemctl status sound-led-daemon.service --no-pager || true
echo ""
echo "  Audio Daemon status:"
systemctl status soundtrigger.service --no-pager || true

echo ""
echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Services will now:"
echo "  • Start automatically on boot"
echo "  • Restart if they crash"
echo "  • Run as user 'soundconsole'"
echo ""
echo "Useful commands:"
echo "  systemctl status sound-led-daemon.service"
echo "  systemctl status soundtrigger.service"
echo "  journalctl -u sound-led-daemon.service -f"
echo "  journalctl -u soundtrigger.service -f"
echo ""
echo "To stop services:"
echo "  sudo systemctl stop sound-led-daemon.service"
echo "  sudo systemctl stop soundtrigger.service"
echo ""

