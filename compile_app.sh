#!/bin/bash
set -e

# ========================================================================
#  PIERRE HUYGHE BALE — Mac App Builder
#  Builds, signs, notarizes, and packages as .pkg + .dmg
# ========================================================================
#
#  PREREQUISITES (one-time setup):
#    1. Install a "Developer ID Application" certificate:
#       https://developer.apple.com/account/resources/certificates/list
#       → Click "+" → "Developer ID Application" → follow CSR steps
#       → Download .cer → double-click to install in Keychain
#
#    2. Find your signing identity:
#       security find-identity -v -p codesigning
#       → Copy the "Developer ID Application: ..." line
#
#    3. Store notarization credentials in Keychain:
#       xcrun notarytool store-credentials "HUYGHE_BALE_NOTARY" \
#           --apple-id "your@email.com" \
#           --team-id "XXXXXXXXXX" \
#           --password "xxxx-xxxx-xxxx-xxxx"
#       (use an app-specific password from https://appleid.apple.com)
#
#    4. Fill in the variables below:
# ========================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load credentials from .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "ERROR: .env file not found. Create one with:"
    echo "  SIGN_IDENTITY=\"Developer ID Application: Your Name (TEAMID)\""
    echo "  NOTARY_PROFILE=\"HUYGHE_BALE_NOTARY\""
    exit 1
fi
BUILD_DIR="$SCRIPT_DIR/admin/build"
BACKEND_DIR="$SCRIPT_DIR/admin/backend"
FRONTEND_DIR="$SCRIPT_DIR/admin/frontend"
VENV="$BACKEND_DIR/.venv/bin"
ICON_PNG="$BUILD_DIR/icon_1024.png"
ICONSET_DIR="$BUILD_DIR/app_icon.iconset"
ICON_ICNS="$BUILD_DIR/app_icon.icns"
APP_NAME="PIERRE HUYGHE BALE"
APPS_DIR="$SCRIPT_DIR/apps"
ENTITLEMENTS="$BUILD_DIR/entitlements.plist"
PKG_SCRIPTS="$BUILD_DIR/pkg_scripts"

echo "========================================"
echo "  PIERRE HUYGHE BALE — Mac App Builder"
echo "========================================"
echo ""

# --- Validate signing identity ---
if [ -z "$SIGN_IDENTITY" ]; then
    echo "ERROR: SIGN_IDENTITY not set in .env file."
    echo ""
    echo "Run this to find your identity:"
    echo "  security find-identity -v -p codesigning"
    echo ""
    echo "Then add to .env: SIGN_IDENTITY=\"Developer ID Application: ...\""
    exit 1
fi

# Verify the identity exists in keychain
if ! security find-identity -v -p codesigning | grep -q "$SIGN_IDENTITY"; then
    echo "ERROR: Signing identity not found in keychain:"
    echo "  $SIGN_IDENTITY"
    echo ""
    echo "Available identities:"
    security find-identity -v -p codesigning
    exit 1
fi

echo "Signing identity: $SIGN_IDENTITY"
echo ""

# --- 1. Install build dependencies ---
echo "=== Installing build dependencies ==="
"$VENV/pip" install --quiet Pillow pywebview pyinstaller
echo ""

# --- 2. Generate icon (if not cached) ---
if [ ! -f "$ICON_ICNS" ]; then
    echo "=== Generating app icon ==="

    "$VENV/python" "$BUILD_DIR/generate_icon.py" "$ICON_PNG"

    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"

    declare -a SIZES=(16 32 64 128 256 512)
    for size in "${SIZES[@]}"; do
        sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
        double=$((size * 2))
        sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
    done
    cp "$ICON_PNG" "$ICONSET_DIR/icon_512x512@2x.png"

    iconutil --convert icns "$ICONSET_DIR" --output "$ICON_ICNS"
    rm -rf "$ICONSET_DIR"

    echo "Icon: $ICON_ICNS"
    echo ""
else
    echo "=== Using cached icon: $ICON_ICNS ==="
    echo ""
fi

# --- 3. Generate VERSION file from current git state ---
echo "=== Generating VERSION file ==="
VERSION_FILE="$BACKEND_DIR/VERSION"
GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)
GIT_DATE=$(git -C "$SCRIPT_DIR" log -1 --format=%ci)
GIT_MSG=$(git -C "$SCRIPT_DIR" log -1 --format=%s)
cat > "$VERSION_FILE" <<VEOF
{"hash": "$GIT_HASH", "date": "$GIT_DATE", "message": "$GIT_MSG"}
VEOF
echo "  Version: $GIT_HASH ($GIT_DATE)"
echo ""

# --- 4. Build frontend ---
echo "=== Building frontend ==="
cd "$FRONTEND_DIR"
npm run build
echo ""

# --- 5. Delete stale .spec file (it overrides CLI flags) ---
rm -f "$BACKEND_DIR/$APP_NAME.spec"

# --- 6. Build Mac .app with PyInstaller ---
echo "=== Building Mac .app ==="
cd "$BACKEND_DIR"
"$VENV/pyinstaller" \
    --name "$APP_NAME" \
    --windowed \
    --noconfirm \
    --icon="$ICON_ICNS" \
    --osx-bundle-identifier "com.pierrehuyghe.bale" \
    --codesign-identity "$SIGN_IDENTITY" \
    --add-data "../frontend/dist:frontend/dist" \
    --add-data "VERSION:." \
    launcher.py
echo ""

# Clean up generated VERSION file
rm -f "$VERSION_FILE"

# --- 7. Copy .app to apps/ ---
echo "=== Copying app to apps/ ==="
mkdir -p "$APPS_DIR"
rm -rf "$APPS_DIR/$APP_NAME.app"
cp -R "$BACKEND_DIR/dist/$APP_NAME.app" "$APPS_DIR/"
APP_PATH="$APPS_DIR/$APP_NAME.app"

# --- 8. Post-process Info.plist ---
echo "=== Updating Info.plist ==="
PLIST="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.pierrehuyghe.bale" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $GIT_HASH" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "$PLIST"
echo ""

# --- 9. Sign inside-out with entitlements ---
echo "=== Signing app (inside-out with hardened runtime) ==="

# 9a. Sign all .dylib and .so files
echo "  Signing libraries..."
find "$APP_PATH/Contents" \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime {} \;

# 9b. Sign .framework bundles (if any)
if [ -d "$APP_PATH/Contents/Frameworks" ]; then
    echo "  Signing frameworks..."
    find "$APP_PATH/Contents/Frameworks" -name "*.framework" -maxdepth 1 \
        -exec codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime {} \;
fi

# 9c. Sign the main executable with entitlements
echo "  Signing main executable..."
codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" \
    "$APP_PATH/Contents/MacOS/$APP_NAME"

# 9d. Sign the outer .app bundle
echo "  Signing app bundle..."
codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" "$APP_PATH"

# Verify
echo "  Verifying signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo ""

# --- 10. Notarize ---
echo "=== Notarizing app (this may take a few minutes) ==="

# Create zip for submission
ZIP_PATH="$APPS_DIR/$APP_NAME.zip"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

# Submit to Apple
xcrun notarytool submit "$ZIP_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait

# Staple the notarization ticket
xcrun stapler staple "$APP_PATH"

# Clean up zip
rm -f "$ZIP_PATH"

echo ""
echo "=== Verifying notarization ==="
spctl --assess --type execute -vvv "$APP_PATH"
echo ""

# --- 11. Build .pkg installer (primary distribution) ---
echo "=== Building .pkg installer ==="
PKG_ROOT="$APPS_DIR/pkg_root"
rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP_PATH" "$PKG_ROOT/Applications/"

PKG_PATH="$APPS_DIR/$APP_NAME.pkg"
pkgbuild \
    --root "$PKG_ROOT" \
    --identifier "com.pierrehuyghe.bale" \
    --version "$GIT_HASH" \
    --install-location "/" \
    --scripts "$PKG_SCRIPTS" \
    "$PKG_PATH"

rm -rf "$PKG_ROOT"
echo ""

# --- 12. Build DMG (fallback) ---
echo "=== Building DMG ==="
DMG_PATH="$APPS_DIR/$APP_NAME.dmg"
rm -f "$DMG_PATH"

DMG_TEMP="$APPS_DIR/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"
cp -R "$APP_PATH" "$DMG_TEMP/"
ln -s /Applications "$DMG_TEMP/Applications"
# Fix_App.command not needed for notarized apps
if [ -f "$SCRIPT_DIR/Fix_App.command" ]; then
    cp "$SCRIPT_DIR/Fix_App.command" "$DMG_TEMP/"
fi

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

rm -rf "$DMG_TEMP"
echo ""

# --- Done ---
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "  App: $APP_PATH"
echo "  PKG: $PKG_PATH  (recommended for distribution)"
echo "  DMG: $DMG_PATH  (fallback)"
echo ""
echo "  The app is signed and notarized."
echo "  Share the .pkg file — recipients just double-click to install."
echo ""
