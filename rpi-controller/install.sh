#!/usr/bin/env bash
set -euo pipefail

echo "=== GPIO OSC Controller Installer ==="

# --- Parse --type=vents|trolley (interactive prompt if missing) ---
DEVICE_TYPE=""
for arg in "$@"; do
    case "$arg" in
        --type=vents|--type=trolley)
            DEVICE_TYPE="${arg#--type=}"
            ;;
        --type=*)
            echo "ERROR: invalid --type value. Use --type=vents or --type=trolley."
            exit 1
            ;;
        --help|-h)
            echo "Usage: sudo bash install.sh [--type=vents|--type=trolley]"
            echo "  If --type is omitted, you'll be prompted."
            exit 0
            ;;
    esac
done

if [ -z "$DEVICE_TYPE" ]; then
    echo "Controller type not provided. Choose one:"
    echo "  1) vents    (ventilation — L298N PWM on GPIO12/13)"
    echo "  2) trolley  (trolley controller — stub, pending hardware spec)"
    read -rp "Enter 1 or 2: " choice
    case "$choice" in
        1) DEVICE_TYPE="vents" ;;
        2) DEVICE_TYPE="trolley" ;;
        *) echo "ERROR: invalid choice"; exit 1 ;;
    esac
fi
echo "Controller type: $DEVICE_TYPE"

# --- Detect install dir and app user ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/gpio_osc.py" ]; then
    APP_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/rpi-controller/gpio_osc.py" ]; then
    APP_DIR="$SCRIPT_DIR/rpi-controller"
else
    echo "ERROR: Cannot find gpio_osc.py relative to $SCRIPT_DIR"
    exit 1
fi

GIT_DIR="$(cd "$APP_DIR" && git rev-parse --show-toplevel 2>/dev/null || echo "$APP_DIR")"
APP_USER="$(stat -c '%U' "$GIT_DIR" 2>/dev/null || stat -f "%Su" "$GIT_DIR")"
APP_USER_HOME="$(getent passwd "$APP_USER" | cut -d: -f6 2>/dev/null || echo "/home/$APP_USER")"

echo "Dossier d'installation : $APP_DIR"
echo "Racine git : $GIT_DIR"
echo "Utilisateur de service : $APP_USER"

sudo -u "$APP_USER" git config --global --add safe.directory "$GIT_DIR" || true

# --- Pi model detection (GPIO deps differ) ---
PI_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "unknown")
echo "Modele detecte : $PI_MODEL"

VENV_OPTS=""
PIP_EXTRA=""
EXTRA_DEPS=""
SKIP_PIP_UPGRADE=0
APT_DEPS=""

case "$PI_MODEL" in
    *"Pi 5"*)
        EXTRA_DEPS="rpi-lgpio>=0.4"
        # rpi-lgpio pulls in lgpio; on recent RPi OS the piwheels wheel is
        # source-only for Python 3.13, so we need swig + liblgpio-dev to build it.
        APT_DEPS="swig liblgpio-dev"
        ;;
    *"Pi 3"*|*"Pi 2"*)
        # Legacy Pi 3/2 (Stretch/Buster). Keep --system-site-packages so the
        # OS-provided python3-rpi.gpio is visible. Also pip-install RPi.GPIO
        # explicitly so things still work when the venv uses a custom Python
        # (rebuilt from source) where system site-packages don't apply.
        VENV_OPTS="--system-site-packages"
        PIP_EXTRA="--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host www.piwheels.org"
        SKIP_PIP_UPGRADE=1
        EXTRA_DEPS="RPi.GPIO>=0.7.0"
        APT_DEPS="build-essential python3-dev"
        ;;
    *)
        # Default (Pi 4, Zero 2, unknown). pip-install RPi.GPIO for the venv
        # in case --system-site-packages can't satisfy it.
        VENV_OPTS="--system-site-packages"
        EXTRA_DEPS="RPi.GPIO>=0.7.0"
        APT_DEPS="build-essential python3-dev"
        ;;
esac

if [ -n "$APT_DEPS" ]; then
    # shellcheck disable=SC2086
    missing=$(for pkg in $APT_DEPS; do dpkg -s "$pkg" >/dev/null 2>&1 || echo "$pkg"; done)
    if [ -n "$missing" ]; then
        echo "Installation des paquets systeme manquants : $missing"
        # shellcheck disable=SC2086
        sudo apt-get update -qq
        # shellcheck disable=SC2086
        sudo apt-get install -y $missing
    fi
fi

echo "Creation de l'environnement virtuel..."
if [ -d "$APP_DIR/venv" ] && [ -n "$VENV_OPTS" ]; then
    if [ -f "$APP_DIR/venv/pyvenv.cfg" ] && grep -q "include-system-site-packages = false" "$APP_DIR/venv/pyvenv.cfg"; then
        echo "Recreation du venv avec --system-site-packages..."
        rm -rf "$APP_DIR/venv"
    fi
fi
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv $VENV_OPTS "$APP_DIR/venv"
fi

PIP_CMD="$APP_DIR/venv/bin/python -m pip"

if [ "$SKIP_PIP_UPGRADE" -eq 0 ]; then
    sudo -u "$APP_USER" $PIP_CMD install $PIP_EXTRA --upgrade pip
fi
sudo -u "$APP_USER" $PIP_CMD install $PIP_EXTRA -r "$APP_DIR/requirements.txt"

if [ -n "$EXTRA_DEPS" ]; then
    echo "Installation de $EXTRA_DEPS..."
    sudo -u "$APP_USER" $PIP_CMD install $EXTRA_DEPS
fi

# --- Identity bootstrap ---
# If no identity yet, create one for this type. If one exists and type differs,
# warn and re-create (explicit opt-in via --type flag to this run).
IDENTITY_DIR="$APP_USER_HOME/.config/gpio-osc"
IDENTITY_FILE="$IDENTITY_DIR/device.json"

sudo -u "$APP_USER" mkdir -p "$IDENTITY_DIR"

if [ -f "$IDENTITY_FILE" ]; then
    EXISTING_TYPE="$(python3 -c "import json,sys; print(json.load(open('$IDENTITY_FILE')).get('type',''))" 2>/dev/null || echo "")"
    if [ -n "$EXISTING_TYPE" ] && [ "$EXISTING_TYPE" != "$DEVICE_TYPE" ]; then
        echo "Identite existante ($EXISTING_TYPE) != type demande ($DEVICE_TYPE). Regeneration..."
        sudo -u "$APP_USER" rm -f "$IDENTITY_FILE"
    else
        echo "Identite existante conservee: $IDENTITY_FILE"
    fi
fi

if [ ! -f "$IDENTITY_FILE" ]; then
    echo "Generation de l'identite ($DEVICE_TYPE)..."
    sudo -u "$APP_USER" GPIO_OSC_TYPE="$DEVICE_TYPE" \
        "$APP_DIR/venv/bin/python" -c "
import sys; sys.path.insert(0, '$APP_DIR')
from identity import load_or_create
ident = load_or_create()
print('Identity:', ident)
"
fi

# --- Disable old unified service if present ---
OLD_SERVICE="gpio-osc"
if systemctl list-unit-files | grep -q "^${OLD_SERVICE}.service"; then
    echo "Desactivation de l'ancien service ${OLD_SERVICE}.service..."
    sudo systemctl stop "$OLD_SERVICE" || true
    sudo systemctl disable "$OLD_SERVICE" || true
    sudo rm -f "/etc/systemd/system/${OLD_SERVICE}.service"
fi
# Also remove any sibling personality service (switching types)
for other in vents trolley; do
    if [ "$other" != "$DEVICE_TYPE" ] && systemctl list-unit-files | grep -q "^gpio-osc-${other}.service"; then
        echo "Desactivation de gpio-osc-${other}.service (type different)..."
        sudo systemctl stop "gpio-osc-${other}" || true
        sudo systemctl disable "gpio-osc-${other}" || true
        sudo rm -f "/etc/systemd/system/gpio-osc-${other}.service"
    fi
done

# --- Generate type-specific systemd unit ---
SERVICE_NAME="gpio-osc-${DEVICE_TYPE}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Generation du service Systemd ($SERVICE_PATH)..."
cat << SYSTEMD_EOF | sudo tee "$SERVICE_PATH" > /dev/null
[Unit]
Description=GPIO OSC Controller (${DEVICE_TYPE}) for HUYGHE
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=GPIO_OSC_TYPE=${DEVICE_TYPE}
ExecStartPre=$APP_DIR/auto_update.sh
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/gpio_osc.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# --- Sudoers: allow APP_USER to restart the service without password ---
echo "Configuration sudoers pour restart sans mot de passe..."
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}"
echo "$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${SERVICE_NAME}" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
# Remove stale sudoers for old unified service
sudo rm -f /etc/sudoers.d/gpio-osc

# --- Enable + start ---
echo "Activation du service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "=== Installation terminée ==="
echo "Type: $DEVICE_TYPE  |  Service: $SERVICE_NAME  |  Identity: $IDENTITY_FILE"
echo "Statut du service (appuie sur 'q' pour quitter si paginé):"
sudo systemctl status "$SERVICE_NAME" --no-pager || true
