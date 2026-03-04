"""MSS App Admin — APK management UI.

Blueprint providing /admin (HTML) and /admin/api/* (JSON) endpoints.

Security:
  - Requires X-MSS-Admin-Token header matching MSS_OPS_TOKEN env var
  - If MSS_OPS_TOKEN is not set, the page loads but API calls return 500
"""

import datetime
import json
import os
import shutil
import urllib.request
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

admin_bp = Blueprint("admin", __name__)

_DOWNLOADS_DIR = Path(os.environ.get("MSS_DOWNLOADS_DIR", "/downloads"))
_APK_FILENAME = "mss.apk"
_VERSION_FILENAME = "version.json"
_ADMIN_TOKEN = os.environ.get("MSS_OPS_TOKEN", "")


# --------------- Auth ---------------

def _admin_guard():
    """Return None if authorized, or a (response, status_code) if denied.

    If MSS_OPS_TOKEN is not set, all requests are allowed.
    """
    if not _ADMIN_TOKEN:
        return None  # No token configured — open access
    provided = request.headers.get("X-MSS-Admin-Token", "")
    if provided != _ADMIN_TOKEN:
        return jsonify({"ok": False, "error": "Invalid admin token"}), 401
    return None


# --------------- Helpers ---------------

def _read_version() -> dict:
    version_file = _DOWNLOADS_DIR / _VERSION_FILENAME
    if version_file.exists():
        try:
            return json.loads(version_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _file_size_str(path: Path) -> str:
    try:
        size = path.stat().st_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    except OSError:
        return "unknown"


def _archive_current_apk():
    """Rename mss.apk to mss_{version}.apk before replacing."""
    current = _DOWNLOADS_DIR / _APK_FILENAME
    if not current.exists():
        return
    version_info = _read_version()
    version_name = version_info.get("version_name", "")
    if version_name:
        archive_name = f"mss_{version_name}.apk"
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"mss_{ts}.apk"
    dest = _DOWNLOADS_DIR / archive_name
    # Avoid overwriting an existing archive
    if dest.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = _DOWNLOADS_DIR / f"mss_{version_name}_{ts}.apk"
    shutil.move(str(current), str(dest))


def _list_apk_files() -> list:
    files = []
    for p in sorted(_DOWNLOADS_DIR.glob("*.apk"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = p.stat()
        files.append({
            "filename": p.name,
            "size": _file_size_str(p),
            "size_bytes": stat.st_size,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "is_current": p.name == _APK_FILENAME,
        })
    return files


# --------------- Routes ---------------

@admin_bp.route("/admin")
def admin_page():
    version_info = _read_version()
    current_apk = _DOWNLOADS_DIR / _APK_FILENAME
    return render_template(
        "admin.html",
        admin_token=_ADMIN_TOKEN,
        version_info=version_info,
        apk_available=current_apk.exists(),
        apk_size=_file_size_str(current_apk) if current_apk.exists() else None,
    )


@admin_bp.route("/admin/api/files")
def admin_files():
    guard = _admin_guard()
    if guard:
        return guard
    return jsonify({"ok": True, "files": _list_apk_files(), "version": _read_version()})


@admin_bp.route("/admin/api/upload", methods=["POST"])
def admin_upload():
    guard = _admin_guard()
    if guard:
        return guard

    f = request.files.get("apk")
    if not f:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    if not f.filename.endswith(".apk"):
        return jsonify({"ok": False, "error": "File must be an .apk"}), 400

    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _archive_current_apk()

    dest = _DOWNLOADS_DIR / _APK_FILENAME
    # Write via temp file for atomicity
    tmp = dest.with_suffix(".tmp")
    try:
        f.save(str(tmp))
        shutil.move(str(tmp), str(dest))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "size": _file_size_str(dest), "files": _list_apk_files()})


@admin_bp.route("/admin/api/upload-url", methods=["POST"])
def admin_upload_url():
    guard = _admin_guard()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "No URL provided"}), 400
    if not (url.startswith("https://") or url.startswith("http://")):
        return jsonify({"ok": False, "error": "URL must start with http:// or https://"}), 400

    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    _archive_current_apk()

    dest = _DOWNLOADS_DIR / _APK_FILENAME
    tmp = dest.with_suffix(".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MSS-Admin/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
        shutil.move(str(tmp), str(dest))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": f"Download failed: {e}"}), 502

    return jsonify({"ok": True, "size": _file_size_str(dest), "files": _list_apk_files()})


@admin_bp.route("/admin/api/version", methods=["POST"])
def admin_version():
    guard = _admin_guard()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    version_info = {
        "version_name": str(data.get("version_name", "")).strip(),
        "version_code": int(data.get("version_code", 0)),
        "release_notes": str(data.get("release_notes", "")).strip(),
        "min_android": str(data.get("min_android", "")).strip(),
    }
    try:
        (_DOWNLOADS_DIR / _VERSION_FILENAME).write_text(
            json.dumps(version_info, indent=2) + "\n"
        )
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "version": version_info})


@admin_bp.route("/admin/api/files/delete", methods=["POST"])
def admin_delete_file():
    guard = _admin_guard()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "No filename provided"}), 400
    if filename == _APK_FILENAME:
        return jsonify({"ok": False, "error": "Cannot delete the current live APK"}), 400
    # Prevent path traversal
    target = (_DOWNLOADS_DIR / filename).resolve()
    if target.parent != _DOWNLOADS_DIR.resolve():
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
    if not target.exists():
        return jsonify({"ok": False, "error": "File not found"}), 404

    target.unlink()
    return jsonify({"ok": True, "files": _list_apk_files()})
