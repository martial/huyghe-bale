#!/bin/bash
# Local-only build of the admin app — no signing, no notarization, no DMG.
# Output: admin/backend/dist/PIERRE HUYGHE BALE.app and a copy in apps/.
# The resulting .app runs on this machine only; for distribution use compile_app.sh.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/admin/build"
BACKEND_DIR="$SCRIPT_DIR/admin/backend"
FRONTEND_DIR="$SCRIPT_DIR/admin/frontend"
VENV="$BACKEND_DIR/.venv/bin"
ICON_PNG="$BUILD_DIR/icon_1024.png"
ICONSET_DIR="$BUILD_DIR/app_icon.iconset"
ICON_ICNS="$BUILD_DIR/app_icon.icns"
APP_NAME="PIERRE HUYGHE BALE"
APPS_DIR="$SCRIPT_DIR/apps"

echo "========================================"
echo "  $APP_NAME — Local (unsigned) build"
echo "========================================"

# --- Bootstrap backend venv if missing ---
if [ ! -x "$VENV/pip" ]; then
    echo "=== Bootstrapping backend venv ==="
    python3 -m venv "$BACKEND_DIR/.venv"
    "$VENV/pip" install --quiet --upgrade pip
    "$VENV/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
fi

# --- Bootstrap frontend node_modules if missing ---
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "=== Installing frontend dependencies ==="
    (cd "$FRONTEND_DIR" && npm install)
fi

# --- Build deps ---
"$VENV/pip" install --quiet Pillow pywebview pyinstaller

# --- Icon (generate once if missing) ---
if [ ! -f "$ICON_ICNS" ]; then
    echo "=== Generating app icon ==="
    "$VENV/python" "$BUILD_DIR/generate_icon.py" "$ICON_PNG"
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"
    for size in 16 32 64 128 256 512; do
        sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
        double=$((size * 2))
        sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
    done
    cp "$ICON_PNG" "$ICONSET_DIR/icon_512x512@2x.png"
    iconutil --convert icns "$ICONSET_DIR" --output "$ICON_ICNS"
    rm -rf "$ICONSET_DIR"
fi

# --- VERSION file (read by the running app) ---
echo "=== Generating VERSION ==="
VERSION_FILE="$BACKEND_DIR/VERSION"
GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)
GIT_DATE=$(git -C "$SCRIPT_DIR" log -1 --format=%ci)
GIT_MSG=$(git -C "$SCRIPT_DIR" log -1 --format=%s)
cat > "$VERSION_FILE" <<VEOF
{"hash": "$GIT_HASH", "date": "$GIT_DATE", "message": "$GIT_MSG"}
VEOF
echo "  Version: $GIT_HASH"

# --- Frontend ---
echo "=== Building frontend ==="
cd "$FRONTEND_DIR"
npm run build

# --- .app via PyInstaller (no signing identity → ad-hoc) ---
echo "=== Building Mac .app ==="
cd "$BACKEND_DIR"
rm -f "$APP_NAME.spec"
"$VENV/pyinstaller" \
    --name "$APP_NAME" \
    --windowed \
    --noconfirm \
    --icon="$ICON_ICNS" \
    --osx-bundle-identifier "com.pierrehuyghe.bale" \
    --add-data "../frontend/dist:frontend/dist" \
    --add-data "VERSION:." \
    launcher.py

rm -f "$VERSION_FILE"

# --- Copy to apps/ ---
mkdir -p "$APPS_DIR"
rm -rf "$APPS_DIR/$APP_NAME.app"
cp -R "$BACKEND_DIR/dist/$APP_NAME.app" "$APPS_DIR/"

# --- Bump version + min macOS in Info.plist (matches compile_app.sh) ---
PLIST="$APPS_DIR/$APP_NAME.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.pierrehuyghe.bale" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $GIT_HASH" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "$PLIST"

echo ""
echo "========================================"
echo "  Local build complete"
echo "========================================"
echo "  $APPS_DIR/$APP_NAME.app"
echo ""
echo "  Runs on this Mac only. Not distributable."
echo "  For signed/notarized distribution, use compile_app.sh."
