#!/usr/bin/env bash
set -euo pipefail

echo "=== GPIO OSC Controller Installer ==="

# Detecter le dossier d'install et le vrai proprietaire (evite que root casse les permissions)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect if we're inside the full repo (rpi-controller is a subfolder)
# or if rpi-controller/ was cloned/copied standalone
if [ -f "$SCRIPT_DIR/gpio_osc.py" ]; then
    APP_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/rpi-controller/gpio_osc.py" ]; then
    APP_DIR="$SCRIPT_DIR/rpi-controller"
else
    echo "ERROR: Cannot find gpio_osc.py relative to $SCRIPT_DIR"
    exit 1
fi

# Git root (for auto_update to pull from)
GIT_DIR="$(cd "$APP_DIR" && git rev-parse --show-toplevel 2>/dev/null || echo "$APP_DIR")"

APP_USER="$(stat -c '%U' "$GIT_DIR" 2>/dev/null || stat -f "%Su" "$GIT_DIR")"

echo "Dossier d'installation detecte : $APP_DIR"
echo "Racine git detectee : $GIT_DIR"
echo "Utilisateur de service detecte : $APP_USER"

# Marquer le repo comme safe directory (requis quand systemd execute sous un autre user)
sudo -u "$APP_USER" git config --global --add safe.directory "$GIT_DIR" || true

# Detection du modele de Pi pour adapter les dependances GPIO
PI_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "unknown")
echo "Modele detecte : $PI_MODEL"

VENV_OPTS=""
PIP_EXTRA=""
EXTRA_DEPS=""
SKIP_PIP_UPGRADE=0

case "$PI_MODEL" in
    *"Pi 5"*)
        # Pi 5 : RPi.GPIO original ne fonctionne pas, il faut rpi-lgpio
        EXTRA_DEPS="rpi-lgpio>=0.4"
        ;;
    *"Pi 3"*|*"Pi 2"*)
        # Pi 3/2 : RPi.GPIO systeme, pip SSL casse sur Stretch
        VENV_OPTS="--system-site-packages"
        PIP_EXTRA="--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host www.piwheels.org"
        SKIP_PIP_UPGRADE=1
        ;;
    *)
        # Pi 4 ou inconnu : RPi.GPIO systeme disponible
        VENV_OPTS="--system-site-packages"
        ;;
esac

# Creer le venv en tant que APP_USER (pas root) pour eviter les problemes de permissions
# Recreer le venv si les options ont change (ex: ajout --system-site-packages)
echo "Creation de l'environnement virtuel..."
if [ -d "$APP_DIR/venv" ] && [ -n "$VENV_OPTS" ]; then
    # Verifier si le venv actuel a --system-site-packages
    if [ -f "$APP_DIR/venv/pyvenv.cfg" ] && grep -q "include-system-site-packages = false" "$APP_DIR/venv/pyvenv.cfg"; then
        echo "Recreation du venv avec --system-site-packages..."
        rm -rf "$APP_DIR/venv"
    fi
fi
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv $VENV_OPTS "$APP_DIR/venv"
fi

if [ "$SKIP_PIP_UPGRADE" -eq 0 ]; then
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install $PIP_EXTRA --upgrade pip
fi
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install $PIP_EXTRA -r "$APP_DIR/requirements.txt"

# Installer la lib GPIO si necessaire (Pi 5 uniquement)
if [ -n "$EXTRA_DEPS" ]; then
    echo "Installation de $EXTRA_DEPS..."
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install $EXTRA_DEPS
fi

# Generer le .service a la volee (pointe vers le dossier git actuel, pas /opt)
SERVICE_NAME="gpio-osc"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Generation du service Systemd ($SERVICE_PATH)..."
cat << SYSTEMD_EOF | sudo tee "$SERVICE_PATH" > /dev/null
[Unit]
Description=GPIO OSC Controller for Ventilation HUYGHE
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStartPre=$APP_DIR/auto_update.sh
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/gpio_osc.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# Sudoers: allow service user to restart gpio-osc without password
echo "Configuration sudoers pour restart sans mot de passe..."
echo "$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart gpio-osc" | sudo tee /etc/sudoers.d/gpio-osc > /dev/null
sudo chmod 0440 /etc/sudoers.d/gpio-osc

# Activer et demarrer le service
echo "Activation du service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "=== Installation terminée ==="
echo "Statut du service (appuie sur 'q' pour quitter si paginé):"
sudo systemctl status "$SERVICE_NAME" --no-pager || true
