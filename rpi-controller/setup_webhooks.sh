#!/usr/bin/env bash
set -euo pipefail

# ─── Interactive Webhook Setup for Monitory ───
# Creates webhooks via the admin API and writes a webhooks.json config file.

DEFAULT_BASE_URL="https://monitory.club"
DEFAULT_EVENTS="start,stop,crash,error"
DEFAULT_OUTPUT="./webhooks.json"

# ─── Helpers ──────────────────────────────────

die() { printf '\033[1;31mError:\033[0m %s\n' "$1" >&2; exit 1; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32mOK\033[0m\n'; }
info() { printf '\033[1;34m→\033[0m %s\n' "$1"; }

# ─── Collect inputs ──────────────────────────

# 1. API Key (hidden)
printf 'Super-admin API key: '
read -rs API_KEY
echo
[ -n "$API_KEY" ] || die "API key cannot be empty."

# 2. Base URL
printf "Base URL [%s]: " "$DEFAULT_BASE_URL"
read -r BASE_URL
BASE_URL="${BASE_URL:-$DEFAULT_BASE_URL}"
# Strip trailing slash
BASE_URL="${BASE_URL%/}"

# 3. Device ID
printf "Device ID: "
read -r DEVICE_ID
[ -n "$DEVICE_ID" ] || die "Device ID cannot be empty."

# 4. Event types
printf "Event types (comma-separated) [%s]: " "$DEFAULT_EVENTS"
read -r EVENTS_INPUT
EVENTS_INPUT="${EVENTS_INPUT:-$DEFAULT_EVENTS}"

# Parse and deduplicate events
IFS=',' read -ra RAW_EVENTS <<< "$EVENTS_INPUT"
EVENTS=()
for evt in "${RAW_EVENTS[@]}"; do
    evt="$(echo "$evt" | xargs)"  # trim whitespace
    [ -z "$evt" ] && continue
    # Check for duplicates in already-collected events
    dup=0
    for existing in "${EVENTS[@]+"${EVENTS[@]}"}"; do
        [ "$existing" = "$evt" ] && dup=1 && break
    done
    if [ "$dup" -eq 1 ]; then
        warn "Duplicate event type '$evt' — skipping."
    else
        EVENTS+=("$evt")
    fi
done
[ ${#EVENTS[@]} -eq 0 ] && die "No valid event types provided."

# 5. Output path
printf "Output path [%s]: " "$DEFAULT_OUTPUT"
read -r OUTPUT_PATH
OUTPUT_PATH="${OUTPUT_PATH:-$DEFAULT_OUTPUT}"

# ─── Create webhooks ─────────────────────────

WEBHOOK_ENTRIES=()
info "Creating ${#EVENTS[@]} webhook(s) for device ${DEVICE_ID}..."
echo

for evt in "${EVENTS[@]}"; do
    printf "  Creating webhook for event '%s'... " "$evt"

    HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST "${BASE_URL}/api/v1/admin/webhooks" \
        -H "Content-Type: application/json" \
        -H "X-Admin-Key: ${API_KEY}" \
        -d "{\"deviceId\": \"${DEVICE_ID}\", \"eventType\": \"${evt}\"}" \
    ) || die "curl failed — check your network connection."

    HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')
    HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -1)

    case "$HTTP_CODE" in
        200|201)
            WEBHOOK_URL=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data['data']['webhookUrl'])
" <<< "$HTTP_BODY") || die "Failed to parse API response."
            ok
            WEBHOOK_ENTRIES+=("{\"url\": \"${WEBHOOK_URL}\", \"events\": [\"${evt}\"]}")
            ;;
        409)
            echo
            # Try to extract existing webhook URL from 409 response
            EXISTING_URL=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data['data']['webhookUrl'])
except Exception:
    pass
" <<< "$HTTP_BODY" 2>/dev/null)
            if [ -n "$EXISTING_URL" ]; then
                warn "Event '$evt' already has a webhook on device $DEVICE_ID — reusing existing URL."
                WEBHOOK_ENTRIES+=("{\"url\": \"${EXISTING_URL}\", \"events\": [\"${evt}\"]}")
            else
                warn "Event '$evt' already has a webhook on device $DEVICE_ID — skipping (could not extract URL)."
            fi
            ;;
        401)
            echo
            die "Unauthorized — check your API key."
            ;;
        404)
            echo
            die "Device $DEVICE_ID not found."
            ;;
        *)
            echo
            ERROR_MSG=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('error', data.get('message', 'Unknown error')))
except Exception:
    print('Unknown error (HTTP $HTTP_CODE)')
" <<< "$HTTP_BODY" 2>/dev/null || echo "Unknown error (HTTP $HTTP_CODE)")
            warn "Failed for event '$evt': $ERROR_MSG — continuing."
            ;;
    esac
done

# ─── Write webhooks.json ─────────────────────

if [ ${#WEBHOOK_ENTRIES[@]} -eq 0 ]; then
    die "No webhooks were created — nothing to write."
fi

# Build JSON with python3 for correct formatting
ENTRIES_JSON=$(printf '%s\n' "${WEBHOOK_ENTRIES[@]}" | python3 -c "
import json, sys
entries = [json.loads(line) for line in sys.stdin if line.strip()]
print(json.dumps({'webhooks': entries}, indent=2))
")

echo "$ENTRIES_JSON" > "$OUTPUT_PATH"

echo
info "Wrote ${#WEBHOOK_ENTRIES[@]} webhook(s) to $OUTPUT_PATH"
echo
cat "$OUTPUT_PATH"
echo
