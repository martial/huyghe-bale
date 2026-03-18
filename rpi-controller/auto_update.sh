#!/usr/bin/env bash
set -e

# Récupération dynamique du dossier où se trouve ce script
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/gpio-osc-updater.log"

cd "$APP_DIR" || exit 1

echo "[$(date)] Checking for updates in $APP_DIR..." >> "$LOG_FILE"

git fetch origin main || { echo "[$(date)] Failed to fetch from origin. Continuing offline." >> "$LOG_FILE"; exit 0; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] Update found! $LOCAL -> $REMOTE" >> "$LOG_FILE"
    git tag -f last_good_state "$LOCAL"
    
    if git pull origin main; then
        echo "[$(date)] Code updated. Installing dependencies..." >> "$LOG_FILE"
        if "$APP_DIR/venv/bin/pip" install -r requirements.txt >> "$LOG_FILE" 2>&1; then
            echo "[$(date)] Update successful." >> "$LOG_FILE"
        else
            echo "[$(date)] PIP install failed. Rolling back..." >> "$LOG_FILE"
            git reset --hard last_good_state
            "$APP_DIR/venv/bin/pip" install -r requirements.txt >> "$LOG_FILE" 2>&1
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
