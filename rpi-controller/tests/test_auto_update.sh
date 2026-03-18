#!/usr/bin/env bash
set -e

pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; exit 1; }

echo "=== Running auto_update.sh Unit Tests ==="

TEST_DIR=$(mktemp -d)
REMOTE_REPO="$TEST_DIR/remote.git"
APP_DIR="$TEST_DIR/gpio-osc"
SCRIPT_TO_TEST="/Users/martial/Documents/Dev/huyghe-bale/rpi-controller/auto_update.sh"

git init --quiet --bare "$REMOTE_REPO"

git clone --quiet "$REMOTE_REPO" "$TEST_DIR/dev"
cd "$TEST_DIR/dev"
echo "v1" > version.txt
echo "requests" > requirements.txt
git add . && git commit --quiet -m "init"
git push --quiet origin main

git clone --quiet "$REMOTE_REPO" "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install --quiet -r requirements.txt

cp "$SCRIPT_TO_TEST" "$APP_DIR/auto_update.sh"
sed -i '' "s|APP_DIR=\"/opt/gpio-osc\"|APP_DIR=\"$APP_DIR\"|g" "$APP_DIR/auto_update.sh"
sed -i '' "s|LOG_FILE=\"/tmp/gpio-osc-updater.log\"|LOG_FILE=\"$TEST_DIR/updater.log\"|g" "$APP_DIR/auto_update.sh"

# Test 1: No update
cd "$APP_DIR"
./auto_update.sh
if grep -q "Already up to date" "$TEST_DIR/updater.log"; then
    pass "Test 1: No update available handles correctly"
else
    fail "Test 1: Failed to report already up to date"
fi

# Test 2: Successful update
cd "$TEST_DIR/dev"
echo "v2" > version.txt
git commit --quiet -am "v2"
git push --quiet origin main

cd "$APP_DIR"
./auto_update.sh
if grep -q "Update successful" "$TEST_DIR/updater.log" && [ "$(cat version.txt)" == "v2" ]; then
    pass "Test 2: Successful update applied correctly"
else
    fail "Test 2: Failed to apply update"
fi

# Test 3: Bad PIP Rollback
cd "$TEST_DIR/dev"
echo "v3" > version.txt
echo "fake-package-9999" > requirements.txt
git commit --quiet -am "v3-bad"
git push --quiet origin main

cd "$APP_DIR"
./auto_update.sh || true
if grep -q "PIP install failed. Rolling back..." "$TEST_DIR/updater.log" && [ "$(cat version.txt)" == "v2" ]; then
    pass "Test 3: Rollback on pip failure works correctly"
else
    fail "Test 3: Failed to rollback on bad pip requirement"
fi

# Test 4: Offline mode
cd "$APP_DIR"
git remote set-url origin /tmp/does-not-exist-repo.git
./auto_update.sh
if grep -q "Failed to fetch from origin. Continuing offline." "$TEST_DIR/updater.log"; then
    pass "Test 4: Offline mode handles failure gracefully and continues"
else
    fail "Test 4: Failed to handle offline mode"
fi

# Cleanup
rm -rf "$TEST_DIR"
echo "All tests passed."
