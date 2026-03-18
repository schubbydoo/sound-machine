#!/bin/bash
set -e

INSTALL_DIR=/opt/propmanager
CONFIG_DIR=/etc/propmanager
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Must run as root ────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root:  sudo bash install.sh"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      Prop Manager — Install / Update     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── If already installed, offer reconfigure or just update ──────
RECONFIGURE=true
if [[ -f "$CONFIG_DIR/config.json" ]]; then
    CURRENT_NAME=$(python3 -c "import json; d=json.load(open('$CONFIG_DIR/config.json')); print(d.get('prop_name','?'))")
    echo "  Existing install found: $CURRENT_NAME"
    echo ""
    read -p "  Reconfigure? [y/N]: " RECONF
    RECONF=${RECONF:-N}
    if [[ ! $RECONF =~ ^[Yy] ]]; then
        RECONFIGURE=false
    fi
    echo ""
fi

# ── Prompt for config ───────────────────────────────────────────
if [[ $RECONFIGURE == true ]]; then
    echo "  Enter prop configuration:"
    echo ""

    read -p "  Prop name (shown in BLE discovery, e.g. 'Zoltar'): " PROP_NAME
    while [[ -z "$PROP_NAME" ]]; do
        echo "  Prop name cannot be empty."
        read -p "  Prop name: " PROP_NAME
    done

    read -p "  WebUI port [8080]: " WEBUI_PORT
    WEBUI_PORT=${WEBUI_PORT:-8080}

    read -p "  Access code (shared secret for app auth): " ACCESS_CODE
    while [[ -z "$ACCESS_CODE" ]]; do
        echo "  Access code cannot be empty."
        read -p "  Access code: " ACCESS_CODE
    done

    read -p "  BLE advertise window in minutes (0 = always on) [10]: " BLE_WINDOW
    BLE_WINDOW=${BLE_WINDOW:-10}

    echo ""
    echo "  ┌─ Configuration ──────────────────────────┐"
    echo "  │  Prop name   : $PROP_NAME"
    echo "  │  WebUI port  : $WEBUI_PORT"
    echo "  │  Access code : $ACCESS_CODE"
    echo "  │  BLE window  : ${BLE_WINDOW} min"
    echo "  └───────────────────────────────────────────┘"
    echo ""
    read -p "  Proceed? [Y/n]: " CONFIRM
    CONFIRM=${CONFIRM:-Y}
    if [[ ! $CONFIRM =~ ^[Yy] ]]; then
        echo "  Aborted."
        exit 0
    fi
    echo ""
fi

# ── Create directories ──────────────────────────────────────────
echo "==> Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"

# ── Store repo path so prop-update.sh can find it later ─────────
echo "$SCRIPT_DIR" > "$INSTALL_DIR/.source_path"

# ── Copy daemon files ───────────────────────────────────────────
echo "==> Copying daemon files..."
cp "$SCRIPT_DIR/daemon.py"        "$INSTALL_DIR/daemon.py"
cp "$SCRIPT_DIR/wifi.py"          "$INSTALL_DIR/wifi.py"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

# ── Python venv ─────────────────────────────────────────────────
echo "==> Setting up Python virtual environment..."
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── Write config (only if reconfiguring) ────────────────────────
if [[ $RECONFIGURE == true ]]; then
    echo "==> Writing config..."
    cat > "$CONFIG_DIR/config.json" << EOF
{
  "prop_name": "$PROP_NAME",
  "webui_port": $WEBUI_PORT,
  "access_code": "$ACCESS_CODE",
  "ble_advertise_window_minutes": $BLE_WINDOW
}
EOF
fi

# ── Install systemd service ──────────────────────────────────────
echo "==> Installing systemd service..."
cp "$SCRIPT_DIR/propmanager.service" /etc/systemd/system/propmanager.service
systemctl daemon-reload
systemctl enable propmanager
systemctl restart propmanager

echo ""
echo "==> Done! Service status:"
echo ""
systemctl status propmanager --no-pager -l
echo ""
echo "  Config: $CONFIG_DIR/config.json"
echo "  Logs:   journalctl -u propmanager -f"
echo ""
