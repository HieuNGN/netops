#!/usr/bin/env bash
# Smoke test for nginx routing between SPA and API.
# Run against the prod stack (docker compose up) or any nginx
# instance serving docker/nginx.conf with the FastAPI backend.
#
# Usage:
#   NGINX_URL=http://localhost:80 BACKEND_URL=http://localhost:8000 \
#     bash tests/nginx_routing.test.sh
#
# Asserts:
#   - SPA page paths return text/html (the React index.html)
#   - /api/* paths proxy to FastAPI and return JSON or 401
#   - Bare API paths (/devices, /checks, /alerts) do NOT return
#     raw JSON on hard refresh
#   - SPA fallback serves index.html for unknown paths
#
# Exit code 0 = all pass, 1 = at least one failure.

set -u

NGINX_URL="${NGINX_URL:-http://localhost:80}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PASS=0
FAIL=0
FAILED_TESTS=()

# ---------- helpers ----------
color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
red()   { color '31' "$1"; }
green() { color '32' "$1"; }
yellow(){ color '33' "$1"; }

assert_spa() {
    # $1=label  $2=path  $3=expected_status (optional, default 200)
    local label="$1" path="$2" expected="${3:-200}"
    local headers status ctype
    headers=$(curl -sS -o /dev/null -D - -H 'Accept: text/html' \
        --max-time 5 "${NGINX_URL}${path}" 2>&1) || {
        red "[FAIL]"; echo " $label  ($path)  curl error"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$label")
        return
    }
    status=$(echo "$headers" | head -1 | awk '{print $2}')
    ctype=$(echo "$headers" | grep -i '^content-type:' | head -1 | tr -d '\r' | awk '{print tolower($2)}')
    if [ "$status" = "$expected" ] && [[ "$ctype" == text/html* ]]; then
        green "[PASS]"; echo " $label  ($path)  $status ${ctype}"
        PASS=$((PASS + 1))
    else
        red "[FAIL]"; echo " $label  ($path)  expected=$expected ${ctype:-?} got=$status ${ctype}"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$label")
    fi
}

assert_api_json() {
    # $1=label  $2=path  $3=expected_status (optional)
    local label="$1" path="$2" expected="${3:-200}"
    local headers status ctype body
    headers=$(curl -sS -o /tmp/opencode/_body.json -D - \
        -H 'Accept: application/json' \
        --max-time 5 "${NGINX_URL}${path}" 2>&1) || {
        red "[FAIL]"; echo " $label  ($path)  curl error"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$label")
        return
    }
    status=$(echo "$headers" | head -1 | awk '{print $2}')
    ctype=$(echo "$headers" | grep -i '^content-type:' | head -1 | tr -d '\r' | awk '{print tolower($2)}')
    body=$(cat /tmp/opencode/_body.json 2>/dev/null || echo '')
    # Accept JSON or auth-failure (401) with JSON detail body
    if [ "$status" = "$expected" ] && [[ "$ctype" == application/json* ]]; then
        green "[PASS]"; echo " $label  ($path)  $status ${ctype}"
        PASS=$((PASS + 1))
    elif [ "$status" = "401" ] && [[ "$ctype" == application/json* ]]; then
        # 401 from /api/auth/me without token is also a valid pass
        green "[PASS]"; echo " $label  ($path)  401 (auth required)"
        PASS=$((PASS + 1))
    else
        red "[FAIL]"; echo " $label  ($path)  expected=$expected application/json got=$status ${ctype:-?} body=${body:0:80}"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$label")
    fi
}

assert_not_json() {
    # Assert path does NOT return raw JSON (e.g. SPA page should
    # return HTML, not the device list).
    local label="$1" path="$2"
    local ctype
    ctype=$(curl -sS -o /dev/null -D - -H 'Accept: text/html' \
        --max-time 5 "${NGINX_URL}${path}" 2>&1 \
        | grep -i '^content-type:' | head -1 | tr -d '\r' | awk '{print tolower($2)}')
    if [[ "$ctype" != application/json* ]]; then
        green "[PASS]"; echo " $label  ($path)  not json (${ctype:-?})"
        PASS=$((PASS + 1))
    else
        red "[FAIL]"; echo " $label  ($path)  returned json when it shouldnt"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$label")
    fi
}

mkdir -p /tmp/opencode

echo "=========================================="
echo " Nginx routing smoke test"
echo " NGINX_URL=${NGINX_URL}"
echo " BACKEND_URL=${BACKEND_URL}"
echo "=========================================="
echo
echo "--- SPA page routes (should be text/html) ---"
assert_spa "Dashboard /"          /
assert_spa "Login /login"         /login
assert_spa "Devices /devices"      /devices
assert_spa "Devices trailing /"    /devices/
assert_spa "Checks /checks"        /checks
assert_spa "Alerts /alerts"        /alerts
assert_spa "Topology /topology"    /topology
assert_spa "Topology trailing /"   /topology/
assert_spa "Topology history"      /topology/history
assert_spa "Settings /settings"    /settings
assert_spa "Unknown route"         /some/random/path

echo
echo "--- API routes via /api prefix (should be JSON) ---"
assert_api_json "Health /api/health"   /api/health
assert_api_json "Stats /api/stats"     /api/stats
assert_api_json "Devices list"         /api/devices
assert_api_json "Topology"             /api/topology
assert_api_json "Checks list"          /api/checks
assert_api_json "Alerts list"          /api/alerts
assert_api_json "Auth me (no token)"   /api/auth/me "" 401

echo
echo "--- Bare API paths (regression: must NOT return raw JSON) ---"
assert_not_json "Bare /devices"       /devices
assert_not_json "Bare /checks"        /checks
assert_not_json "Bare /alerts"        /alerts
assert_not_json "Bare /topology"      /topology
assert_not_json "Bare /topology/hist" /topology/history

echo
echo "=========================================="
printf "Result: %d passed, %d failed\n" "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
    yellow "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
        echo "  - $t"
    done
    exit 1
fi
green "All tests passed."
exit 0
