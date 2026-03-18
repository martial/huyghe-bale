#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IDENTITY="Developer ID Application: Martial Geoffre Rouland (PC5K6NYDF2)"

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
  --codesign-identity "$IDENTITY" \
  --osx-bundle-identifier "com.screenclub.huyghe-bale" \
  launcher.py

echo ""
echo "=== Deep signing ==="
codesign --deep --force --verify --verbose --sign "$IDENTITY" "dist/PIERRE HUYGHE BALE.app"

echo ""
echo "=== Zipping Release ==="
cd dist
rm -f "PIERRE_HUYGHE_BALE.zip"
zip -qr "PIERRE_HUYGHE_BALE.zip" "PIERRE HUYGHE BALE.app"

echo ""
echo "=== Done ==="
echo "App: $SCRIPT_DIR/backend/dist/PIERRE HUYGHE BALE.app"
echo "Zip: $SCRIPT_DIR/backend/dist/PIERRE_HUYGHE_BALE.zip"
