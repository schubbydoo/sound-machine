#!/usr/bin/env bash
# MSS Health Check — returns non-zero if basic checks fail.
# Designed to run on the host (not inside the container).
#
# Usage:  ./scripts/healthcheck.sh
# Exit 0 = healthy, Exit 1 = unhealthy (check stdout for details)

set -euo pipefail

ERRORS=0
WARNINGS=0

ok()   { echo "[OK]   $1"; }
warn() { echo "[WARN] $1"; WARNINGS=$((WARNINGS+1)); }
fail() { echo "[FAIL] $1"; ERRORS=$((ERRORS+1)); }

echo "=== MSS Health Check — $(date -Iseconds) ==="

# 1. Docker container running
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^mss-web$'; then
    ok "Docker container mss-web is running"
else
    fail "Docker container mss-web is NOT running"
fi

# 2. Web API responding
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8080/api/server-info 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    ok "GET /api/server-info returned 200"
else
    fail "GET /api/server-info returned $HTTP_CODE (expected 200)"
fi

# 3. Cloudflared running (optional — warn only)
if systemctl is-active --quiet cloudflared 2>/dev/null; then
    ok "cloudflared service is active"
else
    warn "cloudflared service is not active (tunnel may be down)"
fi

# 4. Disk space check (warn if >90% on /)
DISK_PCT=$(df / --output=pcent | tail -1 | tr -dc '0-9')
if [ "$DISK_PCT" -lt 90 ]; then
    ok "Disk usage: ${DISK_PCT}%"
else
    warn "Disk usage is high: ${DISK_PCT}%"
fi

# 5. DB file exists
DB_PATH="$(cd "$(dirname "$0")/.." && pwd)/cloud-data/data/sound_machine.db"
if [ -f "$DB_PATH" ]; then
    ok "Database file exists at $DB_PATH"
else
    fail "Database file NOT found at $DB_PATH"
fi

echo "=== Summary: $ERRORS failures, $WARNINGS warnings ==="

if [ "$ERRORS" -gt 0 ]; then
    exit 1
fi
exit 0
