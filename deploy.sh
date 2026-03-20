#!/bin/bash
set -e

# ========================================================================
#  PIERRE HUYGHE BALE — Deploy
#  Tags a version, compiles the app, and creates a GitHub release
# ========================================================================
#
#  PREREQUISITES:
#    - gh CLI installed and authenticated (brew install gh && gh auth login)
#    - All compile_app.sh prerequisites (signing identity, notarization, etc.)
#
#  USAGE:
#    ./deploy.sh              # auto-increments patch (v1.0.0 → v1.0.1)
#    ./deploy.sh v2.0.0       # explicit version tag
# ========================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="PIERRE HUYGHE BALE"
DOWNLOAD_NAME="PIERRE-HUYGHE-BALE"
APPS_DIR="$SCRIPT_DIR/apps"
REPO="martial/huyghe-bale"
GCS_BUCKET="gs://apps-screen-club"
REPO_NAME="huyghe-bale"

echo "========================================"
echo "  PIERRE HUYGHE BALE — Deploy"
echo "========================================"
echo ""

# --- Check prerequisites ---
if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not found. Install with: brew install gh"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "ERROR: gh not authenticated. Run: gh auth login"
    exit 1
fi

# --- Ensure working tree is clean ---
if [ -n "$(git -C "$SCRIPT_DIR" status --porcelain --untracked-files=no)" ]; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first."
    git -C "$SCRIPT_DIR" status --short
    exit 1
fi

# --- Determine version tag ---
if [ -n "$1" ]; then
    VERSION="$1"
else
    # Auto-increment: find latest vX.Y.Z tag, bump patch
    LATEST_TAG=$(git -C "$SCRIPT_DIR" tag --list 'v*' --sort=-v:refname | head -1)
    if [ -z "$LATEST_TAG" ]; then
        VERSION="v1.0.0"
    else
        # Parse vX.Y.Z and increment Z
        IFS='.' read -r MAJOR MINOR PATCH <<< "${LATEST_TAG#v}"
        PATCH=$((PATCH + 1))
        VERSION="v${MAJOR}.${MINOR}.${PATCH}"
    fi
fi

GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)
echo "  Version: $VERSION ($GIT_HASH)"
echo ""

# --- Tag the release ---
echo "=== Tagging $VERSION ==="
git -C "$SCRIPT_DIR" tag -a "$VERSION" -m "Release $VERSION"
git -C "$SCRIPT_DIR" push origin "$VERSION"
echo ""

# --- Compile the app ---
echo "=== Running compile_app.sh ==="
bash "$SCRIPT_DIR/compile_app.sh"
echo ""

# --- Create GitHub release with assets ---
echo "=== Creating GitHub release ==="
DMG_PATH="$APPS_DIR/$APP_NAME.dmg"

RELEASE_NOTES="Release $VERSION

Built from commit \`$GIT_HASH\`"

ASSETS=()
if [ -f "$DMG_PATH" ]; then
    ASSETS+=("$DMG_PATH")
fi

gh release create "$VERSION" \
    --repo "$REPO" \
    --title "$VERSION" \
    --notes "$RELEASE_NOTES" \
    "${ASSETS[@]}"

# --- Upload to Google Cloud Storage ---
echo ""
echo "=== Uploading to GCS ==="
GCS_PREFIX="$GCS_BUCKET/$REPO_NAME/$VERSION"

GCS_LINKS=()
if [ -f "$DMG_PATH" ]; then
    gsutil cp "$DMG_PATH" "$GCS_PREFIX/$DOWNLOAD_NAME.dmg"
    GCS_LINKS+=("$GCS_PREFIX/$DOWNLOAD_NAME.dmg")
fi

# Make uploaded files publicly readable
gsutil -m acl ch -r -u AllUsers:R "$GCS_PREFIX/"

echo ""
echo "========================================"
echo "  Deploy complete!"
echo "========================================"
echo ""
echo "  Tag:     $VERSION"
echo "  Commit:  $GIT_HASH"
echo "  Release: https://github.com/$REPO/releases/tag/$VERSION"
echo ""
echo "  Downloads:"
for link in "${GCS_LINKS[@]}"; do
    PUBLIC_URL="${link/gs:\/\//https://storage.googleapis.com/}"
    echo "    $PUBLIC_URL"
done
echo ""
