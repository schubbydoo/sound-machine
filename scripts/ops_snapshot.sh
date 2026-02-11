#!/usr/bin/env bash
# MSS Ops Snapshot — generates a diagnostic archive on the HOST.
# Includes config files, logs, and system info with secrets redacted.
#
# Usage:  ./scripts/ops_snapshot.sh [output_dir]
# Output: mss-ops-snapshot-<timestamp>.tar.gz

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${1:-$(pwd)}"
SNAPSHOT_DIR=$(mktemp -d "/tmp/mss-snapshot-${TIMESTAMP}.XXXXXX")
PREFIX="mss-snapshot-${TIMESTAMP}"

mkdir -p "${SNAPSHOT_DIR}/${PREFIX}"

redact() {
    # Redact common secrets from stdin
    sed -E \
        -e 's/(tunnel:\s*)[0-9a-f-]+/\1<REDACTED>/gi' \
        -e 's/(token['"'"'"]*\s*[:=]\s*['"'"'"]*)[^ '"'"'"]+/\1<REDACTED>/gi' \
        -e 's/(secret['"'"'"]*\s*[:=]\s*['"'"'"]*)[^ '"'"'"]+/\1<REDACTED>/gi' \
        -e 's/(password['"'"'"]*\s*[:=]\s*['"'"'"]*)[^ '"'"'"]+/\1<REDACTED>/gi' \
        -e 's/(MSS_OPS_TOKEN\s*=\s*)\S+/\1<REDACTED>/gi'
}

copy_redacted() {
    local src="$1" dst="$2"
    if [ -f "$src" ]; then
        redact < "$src" > "$dst"
        echo "  + $src"
    else
        echo "  - $src (not found)"
    fi
}

echo "=== MSS Ops Snapshot — ${TIMESTAMP} ==="

# docker-compose.yml
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
copy_redacted "${REPO_DIR}/docker-compose.yml" "${SNAPSHOT_DIR}/${PREFIX}/docker-compose.yml"

# Cloudflared config
mkdir -p "${SNAPSHOT_DIR}/${PREFIX}/cloudflared"
copy_redacted "/etc/cloudflared/config.yml" "${SNAPSHOT_DIR}/${PREFIX}/cloudflared/config.yml"

# Systemd units
mkdir -p "${SNAPSHOT_DIR}/${PREFIX}/systemd"
for f in /etc/systemd/system/cloudflared*; do
    [ -f "$f" ] && copy_redacted "$f" "${SNAPSHOT_DIR}/${PREFIX}/systemd/$(basename "$f")"
done
# Drop-ins
if [ -d "/etc/systemd/system/cloudflared.service.d" ]; then
    mkdir -p "${SNAPSHOT_DIR}/${PREFIX}/systemd/cloudflared.service.d"
    for f in /etc/systemd/system/cloudflared.service.d/*; do
        [ -f "$f" ] && copy_redacted "$f" "${SNAPSHOT_DIR}/${PREFIX}/systemd/cloudflared.service.d/$(basename "$f")"
    done
fi

# Environment report
{
    echo "MSS Ops Snapshot — ${TIMESTAMP}"
    echo "=================================================="
    echo ""
    echo "--- uname -a ---"
    uname -a 2>&1 || echo "FAILED"
    echo ""
    echo "--- df -h ---"
    df -h 2>&1 || echo "FAILED"
    echo ""
    echo "--- free -h ---"
    free -h 2>&1 || echo "FAILED"
    echo ""
    echo "--- uptime ---"
    uptime 2>&1 || echo "FAILED"
    echo ""
    echo "--- ip a ---"
    ip a 2>&1 || echo "FAILED"
    echo ""
    echo "--- docker ps ---"
    docker ps -a 2>&1 || echo "FAILED"
    echo ""
    echo "--- systemctl status cloudflared ---"
    systemctl status cloudflared --no-pager 2>&1 || echo "(not running or not found)"
    echo ""
} > "${SNAPSHOT_DIR}/${PREFIX}/env-report.txt"

# Docker logs (last 1000 lines)
echo "  + docker logs mss-web (last 1000)"
docker logs --tail 1000 mss-web 2>&1 | redact > "${SNAPSHOT_DIR}/${PREFIX}/web-logs.txt" || echo "(failed)" > "${SNAPSHOT_DIR}/${PREFIX}/web-logs.txt"

# Cloudflared logs (last 500 lines)
echo "  + journalctl cloudflared (last 500)"
journalctl -u cloudflared -n 500 --no-pager 2>&1 | redact > "${SNAPSHOT_DIR}/${PREFIX}/cloudflared-logs.txt" || echo "(failed)" > "${SNAPSHOT_DIR}/${PREFIX}/cloudflared-logs.txt"

# Package it
ARCHIVE="${OUTPUT_DIR}/mss-ops-snapshot-${TIMESTAMP}.tar.gz"
tar -czf "$ARCHIVE" -C "${SNAPSHOT_DIR}" "${PREFIX}"
rm -rf "${SNAPSHOT_DIR}"

echo ""
echo "=== Snapshot saved: ${ARCHIVE} ==="
echo "Size: $(du -h "$ARCHIVE" | cut -f1)"
