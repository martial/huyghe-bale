#!/usr/bin/env bash
# -------------------------------------------------------------------
#  PIERRE HUYGHE BALE — Raspberry Pi one-liner bootstrap
# -------------------------------------------------------------------
#
#  Usage (on the Pi, as a sudoer):
#
#    curl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \
#      | sudo bash -s -- --type=vents
#
#  Replace --type=vents with --type=trolley for a trolley controller.
#  If --type is omitted, rpi-controller/install.sh will prompt.
#
#  This script clones the repo into the target user's home, pulls it
#  if already present, then hands off to rpi-controller/install.sh —
#  which owns venv setup, systemd unit generation, and identity file.
# -------------------------------------------------------------------

set -euo pipefail

REPO_URL="https://github.com/martial/huyghe-bale.git"
CLONE_DIR_NAME="huyghe-bale"

# --- Must run as root (pipe: | sudo bash -s -- ...) ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: this script must run as root." >&2
    echo "  Pipe it through sudo, e.g.:" >&2
    echo "    curl -sSL <url> | sudo bash -s -- --type=vents" >&2
    exit 1
fi

# --- Parse --type=... (passed through to rpi-controller/install.sh) ---
INSTALL_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --type=vents|--type=trolley)
            INSTALL_ARGS+=("$arg")
            ;;
        --type=*)
            echo "ERROR: invalid --type value. Use --type=vents or --type=trolley." >&2
            exit 1
            ;;
        --help|-h)
            echo "Usage: curl -sSL <url> | sudo bash -s -- [--type=vents|--type=trolley]"
            exit 0
            ;;
    esac
done

# --- Determine target user (the one who'll own the repo and run the service) ---
TARGET_USER=""
if [ -n "${SUDO_USER-}" ] && [ "$SUDO_USER" != "root" ]; then
    TARGET_USER="$SUDO_USER"
elif id -u pi >/dev/null 2>&1; then
    TARGET_USER="pi"
else
    TARGET_USER="root"
    echo "WARNING: no SUDO_USER and no 'pi' user found — falling back to root." >&2
fi

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [ -z "$TARGET_HOME" ] || [ ! -d "$TARGET_HOME" ]; then
    echo "ERROR: cannot resolve home directory for user '$TARGET_USER'." >&2
    exit 1
fi

CLONE_DIR="$TARGET_HOME/$CLONE_DIR_NAME"

echo "=== Pierre Huyghe Bale — Raspberry Pi installer ==="
echo "  Target user : $TARGET_USER"
echo "  Clone dir   : $CLONE_DIR"
if [ ${#INSTALL_ARGS[@]} -gt 0 ]; then
    echo "  Args        : ${INSTALL_ARGS[*]}"
fi
echo ""

# --- Install git if missing ---
if ! command -v git >/dev/null 2>&1; then
    echo "Installing git..."
    apt-get update -qq
    apt-get install -y -qq git
fi

# --- Clone or update ---
if [ -d "$CLONE_DIR/.git" ]; then
    echo "Repo already present — pulling latest..."
    sudo -u "$TARGET_USER" git -C "$CLONE_DIR" fetch --prune origin
    sudo -u "$TARGET_USER" git -C "$CLONE_DIR" pull --ff-only
else
    echo "Cloning repo into $CLONE_DIR..."
    sudo -u "$TARGET_USER" git clone "$REPO_URL" "$CLONE_DIR"
fi

echo ""
echo "=== Handing off to rpi-controller/install.sh ==="
exec bash "$CLONE_DIR/rpi-controller/install.sh" "${INSTALL_ARGS[@]:-}"
