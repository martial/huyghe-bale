#!/bin/bash
set -e

# ========================================================================
#  PIERRE HUYGHE BALE — Build & Release
#  Triggers GitHub Actions build, waits for artifacts, creates a release.
#
#  Usage:
#    ./release.sh           # auto-increments patch (v1.2.4 → v1.2.5)
#    ./release.sh v2.0.0    # explicit version
#    ./release.sh minor     # auto-increments minor (v1.2.4 → v1.3.0)
#    ./release.sh major     # auto-increments major (v1.2.4 → v2.0.0)
# ========================================================================

REPO="martial/huyghe-bale"

# --- Determine version ---
LATEST=$(gh release list --repo "$REPO" --limit 1 --json tagName -q '.[0].tagName' 2>/dev/null || echo "v0.0.0")
LATEST="${LATEST#v}"
IFS='.' read -r MAJOR MINOR PATCH <<< "$LATEST"

case "${1:-patch}" in
    major)  VERSION="v$((MAJOR + 1)).0.0" ;;
    minor)  VERSION="v${MAJOR}.$((MINOR + 1)).0" ;;
    patch)  VERSION="v${MAJOR}.${MINOR}.$((PATCH + 1))" ;;
    v*)     VERSION="$1" ;;
    *)      echo "Usage: $0 [major|minor|patch|vX.Y.Z]"; exit 1 ;;
esac

echo "========================================"
echo "  PIERRE HUYGHE BALE — Release $VERSION"
echo "========================================"
echo ""
echo "  Latest release: v${LATEST}"
echo "  New release:    $VERSION"
echo ""

# --- Confirm ---
read -r -p "Proceed? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# --- Ensure we're on main and up to date ---
echo ""
echo "=== Checking git state ==="
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: Must be on main branch (currently on $BRANCH)"
    exit 1
fi
git pull --ff-only
echo ""

# --- Tag and push (triggers the build workflow) ---
echo "=== Creating tag $VERSION ==="
git tag -a "$VERSION" -m "Release $VERSION"
git push origin "$VERSION"
echo ""

# --- Wait for the workflow to start ---
echo "=== Waiting for build to start ==="
sleep 5

RUN_ID=""
for i in $(seq 1 12); do
    RUN_ID=$(gh run list --repo "$REPO" --branch "$VERSION" --workflow build.yml --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || true)
    if [ -n "$RUN_ID" ]; then
        break
    fi
    sleep 5
done

if [ -z "$RUN_ID" ]; then
    echo "ERROR: Build workflow did not start. Check GitHub Actions."
    echo "You can create the release manually after the build finishes:"
    echo "  gh run download <run-id> -n macos-dmg -n windows-zip -D /tmp/release"
    echo "  gh release create $VERSION /tmp/release/* --title \"$VERSION\" --generate-notes"
    exit 1
fi

echo "  Build run: https://github.com/$REPO/actions/runs/$RUN_ID"
echo ""

# --- Watch build ---
echo "=== Building macOS + Windows (this takes ~2 min) ==="
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
echo ""

# --- Download artifacts ---
echo "=== Downloading artifacts ==="
ARTIFACTS_DIR=$(mktemp -d)
gh run download "$RUN_ID" --repo "$REPO" -n macos-dmg -D "$ARTIFACTS_DIR/macos"
gh run download "$RUN_ID" --repo "$REPO" -n windows-zip -D "$ARTIFACTS_DIR/windows"

DMG="$ARTIFACTS_DIR/macos/PIERRE HUYGHE BALE.dmg"
ZIP="$ARTIFACTS_DIR/windows/PIERRE HUYGHE BALE - Windows.zip"

echo "  macOS:   $(du -h "$DMG" | cut -f1)"
echo "  Windows: $(du -h "$ZIP" | cut -f1)"
echo ""

# --- Generate release notes ---
NOTES=$(git log --oneline "v${LATEST}..${VERSION}" 2>/dev/null | head -20)
if [ -z "$NOTES" ]; then
    NOTES="Release $VERSION"
fi

# --- Create GitHub release ---
echo "=== Creating GitHub release $VERSION ==="
gh release create "$VERSION" \
    --repo "$REPO" \
    --title "$VERSION" \
    --notes "$(cat <<EOF
## Downloads

| Platform | File |
|----------|------|
| macOS | \`PIERRE HUYGHE BALE.dmg\` (signed & notarized) |
| Windows | \`PIERRE HUYGHE BALE - Windows.zip\` (unsigned) |

## Changes since v${LATEST}

${NOTES}
EOF
)" \
    "$DMG" \
    "$ZIP"

# --- Clean up ---
rm -rf "$ARTIFACTS_DIR"

echo ""
echo "========================================"
echo "  Release $VERSION published!"
echo "========================================"
echo ""
echo "  https://github.com/$REPO/releases/tag/$VERSION"
echo ""
