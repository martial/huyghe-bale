#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/gpio-osc"
SERVICE_NAME="gpio-osc"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== GPIO OSC Controller Installer ==="

# Create install directory
mkdir -p "$INSTALL_DIR"

# Create virtual environment
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Copy application files
cp "$SCRIPT_DIR/gpio_osc.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/"
# Only copy webhooks.json if not already present (preserve local edits)
[ -f "$INSTALL_DIR/webhooks.json" ] || cp "$SCRIPT_DIR/webhooks.json" "$INSTALL_DIR/"

# Install systemd service
cp "$SCRIPT_DIR/gpio-osc.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo "=== Installation complete ==="
echo "Service status:"
systemctl status "$SERVICE_NAME" --no-pager
