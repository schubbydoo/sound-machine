"""MSS Ops Dashboard — remote diagnostics for beta.

Blueprint providing /ops (HTML) and /ops/api/* (JSON) endpoints.

Security:
  - Requires MSS_OPS_ENABLED=1 env var to activate API endpoints
  - Requires X-MSS-Ops-Token header matching MSS_OPS_TOKEN env var
  - The HTML page always loads but shows "Ops disabled" when not enabled
  - Secrets are never logged or returned in responses
"""

import datetime
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from .config import config
from .server_identity import get_server_id, get_server_name

ops_bp = Blueprint("ops", __name__)

# --------------- Configuration ---------------

_OPS_ENABLED = os.environ.get("MSS_OPS_ENABLED", "0") == "1"
_OPS_TOKEN = os.environ.get("MSS_OPS_TOKEN", "")

# Paths inside container that map to host config mounts (see docker-compose.yml)
_HOST_CLOUDFLARED_DIR = Path("/host_etc_cloudflared")
_HOST_SYSTEMD_DIR = Path("/host_etc_systemd")
_HOST_COMPOSE_FILE = Path("/host_config/docker-compose.yml")

# Secrets patterns to redact in snapshot files
_SECRET_PATTERNS = [
    (re.compile(r"(tunnel:\s*)[0-9a-f-]+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(token[\"']?\s*[:=]\s*[\"']?)[^\s\"']+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(secret[\"']?\s*[:=]\s*[\"']?)[^\s\"']+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(password[\"']?\s*[:=]\s*[\"']?)[^\s\"']+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(credentials?[\"']?\s*[:=]\s*[\"']?)[^\s\"']+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\s\"']+", re.IGNORECASE), r"\1<REDACTED>"),
    (re.compile(r"(MSS_OPS_TOKEN\s*=\s*)\S+", re.IGNORECASE), r"\1<REDACTED>"),
]


def _redact(text: str) -> str:
    """Redact secrets from text content."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# --------------- Auth helpers ---------------

def _ops_api_guard():
    """Check that ops is enabled and token is valid.

    Returns None if authorized, or a (response, status_code) tuple if denied.
    """
    if not _OPS_ENABLED:
        return jsonify({"ok": False, "error": "Ops not enabled"}), 403
    if not _OPS_TOKEN:
        return jsonify({"ok": False, "error": "Ops token not configured"}), 500
    provided = request.headers.get("X-MSS-Ops-Token", "")
    if provided != _OPS_TOKEN:
        return jsonify({"ok": False, "error": "Invalid ops token"}), 401
    return None


# --------------- Subprocess helpers ---------------

def _run(cmd, timeout=10):
    """Run a command and return (stdout, ok)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode == 0
    except FileNotFoundError:
        return f"command not found: {cmd[0]}", False
    except subprocess.TimeoutExpired:
        return "timeout", False
    except Exception as e:
        return str(e), False


def _docker_api(path, timeout=5):
    """Call Docker Engine API via the socket using curl.

    Returns (parsed_json_or_text, ok).
    """
    sock = "/var/run/docker.sock"
    if not os.path.exists(sock):
        return "Docker socket not available", False
    try:
        result = subprocess.run(
            ["curl", "-s", "--unix-socket", sock, f"http://localhost{path}"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return result.stderr.strip(), False
        try:
            return json.loads(result.stdout), True
        except json.JSONDecodeError:
            return result.stdout.strip(), True
    except Exception as e:
        return str(e), False


# --------------- Git SHA helper ---------------

def _get_git_sha():
    """Try to get git commit SHA from multiple sources."""
    # Try .git-sha file (baked into image at build time)
    sha_file = config.root / ".git-sha"
    if sha_file.exists():
        return sha_file.read_text().strip()[:12]
    # Try git command
    out, ok = _run(["git", "-C", str(config.root), "rev-parse", "--short=12", "HEAD"])
    if ok:
        return out
    return "unknown"


# --------------- DB helpers ---------------

def _db_stats():
    """Get database statistics."""
    db_path = config.db_path
    if not db_path.exists():
        return {"exists": False}

    stats = {"exists": True, "size_bytes": db_path.stat().st_size}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Count trackpacks (profiles)
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM profiles").fetchone()
            stats["trackpack_count"] = row["cnt"]
        except sqlite3.OperationalError:
            stats["trackpack_count"] = 0

        # Count audio files
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM audio_files").fetchone()
            stats["audio_file_count"] = row["cnt"]
        except sqlite3.OperationalError:
            stats["audio_file_count"] = 0

        # All trackpack names and published state
        try:
            rows = conn.execute(
                "SELECT id, name, published FROM profiles ORDER BY name"
            ).fetchall()
            stats["recent_trackpacks"] = [
                {"id": r["id"], "name": r["name"], "published": bool(r["published"])}
                for r in rows
            ]
        except sqlite3.OperationalError:
            stats["recent_trackpacks"] = []

        conn.close()
    except Exception as e:
        stats["error"] = str(e)

    return stats


# --------------- Routes: HTML ---------------

@ops_bp.route("/ops")
def ops_page():
    """Serve the ops dashboard HTML page.

    Always loads (even if ops is disabled) — shows friendly message.
    The page itself uses JS to call /ops/api/* with the token.
    """
    return render_template("ops.html", ops_enabled=_OPS_ENABLED, ops_token=_OPS_TOKEN)


# --------------- Routes: API ---------------

@ops_bp.route("/ops/api/health")
def ops_health():
    """Application-level health check.

    Returns app status, configuration, DB stats, trackpack info.
    """
    denied = _ops_api_guard()
    if denied:
        return denied

    db = _db_stats()

    return jsonify({
        "ok": True,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "app": {
            "up": True,
            "version": _get_git_sha(),
            "server_id": get_server_id(config.data_dir),
            "server_name": get_server_name(config.data_dir),
        },
        "paths": {
            "root": str(config.root),
            "data_dir": str(config.data_dir),
            "sounds_dir": str(config.sounds_dir),
            "db_path": str(config.db_path),
        },
        "database": db,
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "uptime": _run(["uptime", "-p"])[0],
        },
    })


@ops_bp.route("/ops/api/status")
def ops_status():
    """Infrastructure status: Docker, ports, cloudflared."""
    denied = _ops_api_guard()
    if denied:
        return denied

    # Docker container status via API
    docker_status = {"available": False}
    containers, ok = _docker_api("/containers/json?all=true")
    if ok and isinstance(containers, list):
        docker_status["available"] = True
        for c in containers:
            names = c.get("Names", [])
            if any("/mss-web" in n for n in names):
                docker_status["mss_web"] = {
                    "state": c.get("State", "unknown"),
                    "status": c.get("Status", "unknown"),
                    "image": c.get("Image", "unknown"),
                    "created": c.get("Created", 0),
                }
                break
        else:
            docker_status["mss_web"] = {"state": "not found"}

    # Port checks
    port_checks = {}
    for port, label in [(8080, "web")]:
        out, ok = _run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                         f"http://localhost:{port}/api/server-info"], timeout=5)
        port_checks[label] = {"port": port, "http_status": out, "ok": ok and out == "200"}

    # Cloudflared (from host mount)
    cf_status = {"config_found": False}
    cf_config = _HOST_CLOUDFLARED_DIR / "config.yml"
    if cf_config.exists():
        cf_status["config_found"] = True
        try:
            content = cf_config.read_text()
            cf_status["config_preview"] = _redact(content[:500])
        except Exception:
            pass

    # Disk and memory
    df_out, _ = _run(["df", "-h", "/"])
    free_out, _ = _run(["free", "-h"])

    return jsonify({
        "ok": True,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "docker": docker_status,
        "ports": port_checks,
        "cloudflared": cf_status,
        "disk": df_out,
        "memory": free_out,
    })


@ops_bp.route("/ops/api/logs")
def ops_logs():
    """Retrieve recent log lines.

    Query params:
      source: "web" (docker logs) or "cloudflared" (journalctl via host mount)
      lines: number of lines (default 200, max 2000)
    """
    denied = _ops_api_guard()
    if denied:
        return denied

    source = request.args.get("source", "web")
    try:
        lines = min(int(request.args.get("lines", 200)), 2000)
    except (ValueError, TypeError):
        lines = 200

    if source == "web":
        # Get docker logs via API
        data, ok = _docker_api(
            f"/containers/mss-web/logs?stdout=true&stderr=true&tail={lines}",
            timeout=10,
        )
        if ok:
            # Docker log API returns raw bytes with header frames
            # For text output, strip the 8-byte docker log header per line
            if isinstance(data, str):
                log_lines = []
                for line in data.split("\n"):
                    # Docker multiplexed stream: first 8 bytes are header
                    if len(line) > 8:
                        log_lines.append(line[8:])
                    else:
                        log_lines.append(line)
                log_text = "\n".join(log_lines)
            else:
                log_text = str(data)
        else:
            # Fallback: try reading gunicorn log file in mounted volume
            log_file = config.log_dir / "gunicorn.log"
            if log_file.exists():
                try:
                    all_lines = log_file.read_text().splitlines()
                    log_text = "\n".join(all_lines[-lines:])
                except Exception as e:
                    log_text = f"Error reading log file: {e}"
            else:
                log_text = f"Docker socket unavailable and no log file at {log_file}"

    elif source == "cloudflared":
        # Try journalctl via host journal mount
        journal_dir = Path("/host_journal")
        if journal_dir.exists():
            out, ok = _run(
                ["journalctl", f"--directory={journal_dir}", "-u", "cloudflared",
                 "-n", str(lines), "--no-pager"],
                timeout=10,
            )
            log_text = out if ok else f"journalctl failed: {out}"
        else:
            log_text = (
                "Cloudflared logs are only available from the host (not inside the container).\n"
                "\n"
                "To view cloudflared logs, SSH into the VM and run:\n"
                "\n"
                "    sudo journalctl -u cloudflared -n 200 --no-pager\n"
                "\n"
                "To follow logs in real time:\n"
                "\n"
                "    sudo journalctl -u cloudflared -f\n"
                "\n"
                "To check if cloudflared is running:\n"
                "\n"
                "    sudo systemctl status cloudflared\n"
            )
    else:
        return jsonify({"ok": False, "error": f"Unknown source: {source}"}), 400

    return jsonify({
        "ok": True,
        "source": source,
        "lines_requested": lines,
        "log": _redact(log_text),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    })


@ops_bp.route("/ops/api/snapshot")
def ops_snapshot():
    """Generate and download a diagnostic snapshot as tar.gz.

    Includes config files, env report, and system info.
    All secrets are redacted.
    """
    denied = _ops_api_guard()
    if denied:
        return denied

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"mss-ops-snapshot-{timestamp}.tar.gz"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        prefix = f"mss-snapshot-{timestamp}"

        def _add_text(name, text):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name=f"{prefix}/{name}")
            info.size = len(data)
            info.mtime = time.time()
            tar.addfile(info, io.BytesIO(data))

        # docker-compose.yml from host mount
        if _HOST_COMPOSE_FILE.exists():
            try:
                content = _HOST_COMPOSE_FILE.read_text()
                _add_text("docker-compose.yml", _redact(content))
            except Exception as e:
                _add_text("docker-compose.yml.error", str(e))

        # cloudflared config
        cf_config = _HOST_CLOUDFLARED_DIR / "config.yml"
        if cf_config.exists():
            try:
                content = cf_config.read_text()
                _add_text("cloudflared/config.yml", _redact(content))
            except Exception as e:
                _add_text("cloudflared/config.yml.error", str(e))

        # cloudflared service files
        if _HOST_SYSTEMD_DIR.exists():
            for f in _HOST_SYSTEMD_DIR.iterdir():
                if "cloudflared" in f.name:
                    try:
                        content = f.read_text()
                        _add_text(f"systemd/{f.name}", _redact(content))
                    except Exception:
                        pass
            # Check drop-ins
            dropin_dir = _HOST_SYSTEMD_DIR / "cloudflared.service.d"
            if dropin_dir.exists():
                for f in dropin_dir.iterdir():
                    try:
                        content = f.read_text()
                        _add_text(f"systemd/cloudflared.service.d/{f.name}", _redact(content))
                    except Exception:
                        pass

        # Environment report
        env_commands = [
            ("uname -a", ["uname", "-a"]),
            ("df -h", ["df", "-h"]),
            ("free -h", ["free", "-h"]),
            ("uptime", ["uptime"]),
            ("ip a", ["ip", "a"]),
        ]

        report_lines = [
            f"MSS Ops Snapshot — {timestamp}",
            "=" * 50,
            "",
        ]

        for label, cmd in env_commands:
            out, ok = _run(cmd)
            report_lines.append(f"--- {label} ---")
            report_lines.append(out if ok else f"FAILED: {out}")
            report_lines.append("")

        # Docker ps via API
        containers, ok = _docker_api("/containers/json?all=true")
        report_lines.append("--- docker ps ---")
        if ok and isinstance(containers, list):
            for c in containers:
                names = ", ".join(c.get("Names", []))
                state = c.get("State", "?")
                status = c.get("Status", "?")
                image = c.get("Image", "?")
                report_lines.append(f"  {names}  [{state}] {status}  ({image})")
        else:
            report_lines.append(f"  Docker API unavailable: {containers}")
        report_lines.append("")

        # MSS config
        report_lines.append("--- MSS Configuration ---")
        report_lines.append(f"  Root:       {config.root}")
        report_lines.append(f"  Data dir:   {config.data_dir}")
        report_lines.append(f"  Sounds dir: {config.sounds_dir}")
        report_lines.append(f"  DB path:    {config.db_path}")
        report_lines.append(f"  DB exists:  {config.db_path.exists()}")
        report_lines.append("")

        # DB stats
        report_lines.append("--- Database Stats ---")
        db = _db_stats()
        for k, v in db.items():
            report_lines.append(f"  {k}: {v}")
        report_lines.append("")

        _add_text("env-report.txt", _redact("\n".join(report_lines)))

        # Recent web logs (last 500 lines)
        data, ok = _docker_api(
            "/containers/mss-web/logs?stdout=true&stderr=true&tail=500",
            timeout=10,
        )
        if ok and isinstance(data, str):
            _add_text("web-logs.txt", _redact(data))

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/gzip",
        as_attachment=True,
        download_name=filename,
    )
