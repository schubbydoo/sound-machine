"""MSS App Download Page — serves APK for Android sideloading.

Blueprint providing /app (HTML landing page), /app/download (APK file),
and /app/api/version (JSON version info for in-app update checks).

Configuration:
  - MSS_DOWNLOADS_DIR env var sets the directory containing mss.apk
  - Optional version.json alongside the APK provides version metadata
"""

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, send_file

app_download_bp = Blueprint("app_download", __name__)

_DOWNLOADS_DIR = Path(os.environ.get("MSS_DOWNLOADS_DIR", "/downloads"))
_APK_FILENAME = "mss.apk"


def _get_apk_path() -> Path:
    return _DOWNLOADS_DIR / _APK_FILENAME


def _get_version_info() -> dict:
    """Read version.json from the downloads directory if it exists."""
    version_file = _DOWNLOADS_DIR / "version.json"
    if version_file.exists():
        try:
            return json.loads(version_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _get_apk_size(apk_path: Path) -> str:
    """Return human-readable file size."""
    try:
        size = apk_path.stat().st_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    except OSError:
        return "unknown"


# --------------- Routes ---------------

@app_download_bp.route("/app")
def app_page():
    """Landing page with download button and install instructions."""
    apk_path = _get_apk_path()
    apk_available = apk_path.exists()
    version_info = _get_version_info()
    apk_size = _get_apk_size(apk_path) if apk_available else None

    return render_template(
        "app_download.html",
        apk_available=apk_available,
        apk_size=apk_size,
        version_name=version_info.get("version_name", ""),
        release_notes=version_info.get("release_notes", ""),
        min_android=version_info.get("min_android", ""),
    )


@app_download_bp.route("/app/download")
def app_download():
    """Serve the APK file."""
    apk_path = _get_apk_path()
    if not apk_path.exists():
        return jsonify({"ok": False, "error": "APK not available"}), 404

    return send_file(
        apk_path,
        mimetype="application/vnd.android.package-archive",
        as_attachment=True,
        download_name=_APK_FILENAME,
    )


@app_download_bp.route("/app/api/version")
def app_version():
    """JSON version endpoint for in-app update checks."""
    apk_path = _get_apk_path()
    version_info = _get_version_info()

    return jsonify({
        "ok": True,
        "available": apk_path.exists(),
        "version_name": version_info.get("version_name", ""),
        "version_code": version_info.get("version_code", 0),
        "release_notes": version_info.get("release_notes", ""),
        "min_android": version_info.get("min_android", ""),
        "download_url": "/app/download",
        "file_size": _get_apk_size(apk_path) if apk_path.exists() else None,
    })
