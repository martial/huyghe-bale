#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Building frontend ==="
cd "$SCRIPT_DIR/frontend"
npm run build

echo ""
echo "=== Installing Python build dependencies ==="
cd "$SCRIPT_DIR/backend"
.venv/bin/pip install pywebview pyinstaller

echo ""
echo "=== Building Mac .app with PyInstaller ==="
.venv/bin/pyinstaller \
  --name "PIERRE HUYGHE BALE" \
  --windowed \
  --noconfirm \
  --add-data "../frontend/dist:frontend/dist" \
  launcher.py

echo ""
echo "=== Done ==="
echo "App: $SCRIPT_DIR/backend/dist/PIERRE HUYGHE BALE.app"
echo ""
echo "To distribute: zip -r 'PIERRE HUYGHE BALE.zip' 'dist/PIERRE HUYGHE BALE.app'"
echo "Recipients: right-click → Open on first launch (unsigned app)"
