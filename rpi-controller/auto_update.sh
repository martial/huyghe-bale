#!/usr/bin/env bash
set -e

# Récupération dynamique du dossier où se trouve ce script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/gpio-osc-updater.log"

# Use the git root for pull operations
GIT_DIR="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR")"
cd "$GIT_DIR" || exit 1

# Detect APP_DIR (where gpio_osc.py, venv, requirements.txt live)
if [ -f "$SCRIPT_DIR/gpio_osc.py" ]; then
    APP_DIR="$SCRIPT_DIR"
else
    APP_DIR="$GIT_DIR/rpi-controller"
fi

echo "[$(date)] Checking for updates in $GIT_DIR..." >> "$LOG_FILE"

git fetch origin main || { echo "[$(date)] Failed to fetch from origin. Continuing offline." >> "$LOG_FILE"; exit 0; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] Update found! $LOCAL -> $REMOTE" >> "$LOG_FILE"
    git tag -f last_good_state "$LOCAL"

    # Flags pip pour compatibilite Pi 3 (SSL casse sur Stretch)
    PIP_EXTRA="--trusted-host pypi.org --trusted-host files.pythonhosted.org"

    if git pull origin main; then
        echo "[$(date)] Code updated. Installing dependencies..." >> "$LOG_FILE"
        if "$APP_DIR/venv/bin/python" -m pip install $PIP_EXTRA -r "$APP_DIR/requirements.txt" >> "$LOG_FILE" 2>&1; then
            echo "[$(date)] Update successful." >> "$LOG_FILE"
        else
            echo "[$(date)] PIP install failed. Rolling back..." >> "$LOG_FILE"
            git reset --hard last_good_state
            "$APP_DIR/venv/bin/python" -m pip install $PIP_EXTRA -r "$APP_DIR/requirements.txt" >> "$LOG_FILE" 2>&1
            exit 1
        fi
    else
        echo "[$(date)] Git pull failed. Rolling back..." >> "$LOG_FILE"
        git reset --hard last_good_state
        exit 1
    fi
else
    echo "[$(date)] Already up to date." >> "$LOG_FILE"
fi
exit 0
