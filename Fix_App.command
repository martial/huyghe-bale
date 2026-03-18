#!/bin/bash
# Fix_App.command — Remove quarantine from PIERRE HUYGHE BALE
# Double-click this file if the app won't open after dragging to Applications.

APP_NAME="PIERRE HUYGHE BALE"
APP_FOUND=""

# Search common locations
for dir in "/Applications" "$HOME/Applications" "$HOME/Desktop"; do
    if [ -d "$dir/$APP_NAME.app" ]; then
        APP_FOUND="$dir/$APP_NAME.app"
        break
    fi
done

if [ -z "$APP_FOUND" ]; then
    osascript -e "display dialog \"Could not find '$APP_NAME.app' in Applications or Desktop.\\n\\nPlease drag the app to your Applications folder first, then run this script again.\" buttons {\"OK\"} default button \"OK\" with title \"$APP_NAME\" with icon caution"
    exit 1
fi

# Remove quarantine
xattr -cr "$APP_FOUND"

# Notify and offer to launch
RESULT=$(osascript -e "display dialog \"Security fix applied!\\n\\nThe app is now ready to use.\" buttons {\"Open App\", \"Close\"} default button \"Open App\" with title \"$APP_NAME\" with icon note" 2>/dev/null)

if echo "$RESULT" | grep -q "Open App"; then
    open "$APP_FOUND"
fi
