#!/usr/bin/env bash
set -euo pipefail

echo "=== GPIO OSC Controller Installer ==="

# 1. Identifier le dossier d'installation et l'utilisateur propriétaire
# Qu'est-ce qui pourrait mal se passer ? 
# Si l'utilisateur lance "sudo ./install.sh", l'utilisateur courant devient "root".
# Si root effectue des "git pull" (via l'auto-update) ou installe des libs Python, 
# il modifiera les permissions du dossier. L'utilisateur 'pi' (ou autre) ne pourra plus développer, 
# et ssh-agent ne passera potentiellement pas si root n'a pas les clés Github.
# Solution : On détecte le vrai propriétaire du dossier actuel via "stat" et on force toutes 
# les opérations locales à utiliser cet utilisateur.
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="$(stat -c '%U' "$APP_DIR" 2>/dev/null || stat -f "%Su" "$APP_DIR")"

echo "Dossier d'installation detecte : $APP_DIR"
echo "Utilisateur de service detecte : $APP_USER"

# 2. Sécuriser le dossier Git (Safe Directory)
# Qu'est-ce qui pourrait mal se passer ? 
# Systemd lance parfois le service (et donc auto_update.sh) avec des contextes stricts.
# Depuis CVE-2022-24765, Git refuse d'opérer sur un repo possédé par un utilisateur différent
# du contexte d'exécution.
# Solution : On ajoute explicitement ce dossier dans la config git globale de l'utilisateur.
sudo -u "$APP_USER" git config --global --add safe.directory "$APP_DIR" || true

# 3. Création du Virtual Environment
# Qu'est-ce qui pourrait mal se passer ?
# Si "venv" est créé par root, l'auto-update lancé par $APP_USER échouera avec une erreur "Permission denied"
# au moment de faire "pip install".
# Solution : On lance la commande "python3 -m venv" et "pip install" en tant que APP_USER via sudo -u.
echo "Creation de l'environnement virtuel..."
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
fi
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4. Génération dynamique du service Systemd
# Qu'est-ce qui pourrait mal se passer ?
# L'ancien script copiait des fichiers vers /opt/gpio-osc et installait un fichier service statique.
# Si l'utilisateur met à jour le code dans son dossier /home/pi/huyghe-bale, les modifications n'auraient
# jamais été prises en compte (puisque le service tournait dans /opt). De plus, l'auto-update git 
# nécessite que le dossier soit un dépôt Git valide !
# Solution : On génère le fichier .service à la volée. Il pointera directement vers le dossier Git 
# actuel ($APP_DIR) et tournera sous l'identité de l'utilisateur qui a cloné le repo ($APP_USER).
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

# 5. Activation et démarrage
# Qu'est-ce qui pourrait mal se passer ?
# Si systemd n'est pas rechargé après la création du fichier, il ignorera le nouveau service.
# Si le service crashe au démarrage, l'installation semble réussie alors qu'elle ne l'est pas.
# Solution : daemon-reload systématique, et affichage du statut final pour repérer les erreurs de suite.
echo "Activation du service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "=== Installation terminée ==="
echo "Statut du service (appuie sur 'q' pour quitter si paginé):"
sudo systemctl status "$SERVICE_NAME" --no-pager || true
