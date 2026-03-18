#!/usr/bin/env bash
set -e

APP_DIR="/opt/gpio-osc"
LOG_FILE="/var/log/gpio-osc-updater.log"
cd "$APP_DIR" || exit 1

echo "[$(date)] Checking for updates..." >> "$LOG_FILE"

# Make sure we have the latest info
git fetch origin main || { echo "[$(date)] Failed to fetch from origin. Continuing offline." >> "$LOG_FILE"; exit 0; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] Update found! $LOCAL -> $REMOTE" >> "$LOG_FILE"
    
    # Save the current state in a tag so we can rollback if needed
    git tag -f last_good_state "$LOCAL"
    
    # Try pulling
    if git pull origin main; then
        echo "[$(date)] Code updated. Installing dependencies..." >> "$LOG_FILE"
        if "$APP_DIR/venv/bin/pip" install -r requirements.txt >> "$LOG_FILE" 2>&1; then
            echo "[$(date)] Update successful." >> "$LOG_FILE"
            # Keep track of when we last updated
            echo "$REMOTE" > "$APP_DIR/.last_update_hash"
        else
            echo "[$(date)] PIP install failed. Rolling back..." >> "$LOG_FILE"
            git reset --hard last_good_state
            # Re-install previous dependencies
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
