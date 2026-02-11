#!/usr/bin/env python3
import json
import os
import shutil
import tempfile
import contextlib
import wave
import sqlite3
import datetime
import threading
import subprocess
import shlex
import time
import hashlib
import zipfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response

try:
    from werkzeug.utils import secure_filename
except ImportError:
    from werkzeug.utils import secure_filename

from . import network_utils as nu
from .storage import get_storage_adapter, get_trackpack_updated_at as storage_get_updated_at
from .server_identity import get_server_id, get_server_name
from .config import config
from .ops import ops_bp

# Path configuration - all paths come from centralized config module
DB_PATH = config.db_path
SOUNDS_ROOT = config.sounds_dir
EXPORTS_DIR = config.exports_dir
DATA_DIR = config.data_dir

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit
app.register_blueprint(ops_bp)

# Startup validation: log paths, create directories, validate configuration
# fail_fast=False allows the app to start even if some checks fail (e.g., DB not yet created)
_startup_errors = config.startup(fail_fast=False)

# ---------------- Database Helpers ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    conn = get_db()
    try:
        cur = conn.execute(query, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def get_system_config(key, default=None):
    row = query_db("SELECT value FROM system_config WHERE key = ?", (key,), one=True)
    return row['value'] if row else default

def set_system_config(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# ---------------- Audio File Management ----------------

TARGET_RATE = 44100
TARGET_WIDTH_BYTES = 2

def _have_cmd(cmd):
    return shutil.which(cmd) is not None

def probe_wav(path):
    try:
        with contextlib.closing(wave.open(str(path), 'rb')) as w:
            return {
                'channels': w.getnchannels(),
                'sampwidth': w.getsampwidth(),
                'framerate': w.getframerate(),
                'nframes': w.getnframes(),
            }
    except Exception:
        return {}

def needs_conversion(path):
    info = probe_wav(path)
    if not info: return True
    if info['sampwidth'] != TARGET_WIDTH_BYTES: return True
    if info['framerate'] != TARGET_RATE: return True
    if info['channels'] not in (1, 2): return True
    return False

def convert_wav(src, dst):
    if _have_cmd('sox'):
        cmd = ['sox', str(src), '-r', str(TARGET_RATE), '-e', 'signed-integer', '-b', '16', str(dst)]
    elif _have_cmd('ffmpeg'):
        cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-ar', str(TARGET_RATE), '-acodec', 'pcm_s16le', str(dst)]
    else:
        raise RuntimeError('No conversion tool found')
    subprocess.check_call(cmd)

def sync_files_to_db():
    """Scans SOUNDS_ROOT and ensures DB is up to date."""
    if not SOUNDS_ROOT.exists():
        SOUNDS_ROOT.mkdir(parents=True, exist_ok=True)
    
    # Get all wavs on disk
    disk_files = {}
    for p in SOUNDS_ROOT.rglob('*.wav'):
        disk_files[str(p.resolve())] = p.name

    conn = get_db()
    # Get all DB files
    db_files = {row['filepath']: row['id'] for row in conn.execute("SELECT id, filepath FROM audio_files").fetchall()}
    
    # Add new
    for path_str, name in disk_files.items():
        if path_str not in db_files:
            conn.execute("INSERT INTO audio_files (filename, filepath) VALUES (?, ?)", (name, path_str))
            
    conn.commit()
    conn.close()

# ---------------- Routes ----------------

@app.route('/')
def index():
    sync_files_to_db()
    
    conn = get_db()
    profiles = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
    
    active_profile_id = request.args.get('profile_id')
    if not active_profile_id and profiles:
        active_profile_id = profiles[0]['id']
    
    mappings = {}
    if active_profile_id:
        rows = conn.execute("""
            SELECT bm.button_id, af.filename, af.description, af.category, af.hint, af.id as audio_id
            FROM button_mappings bm
            JOIN audio_files af ON bm.audio_file_id = af.id
            WHERE bm.profile_id = ?
        """, (active_profile_id,)).fetchall()
        for r in rows:
            mappings[r['button_id']] = dict(r)

    channels = {}
    c_rows = conn.execute("""
        SELECT c.channel_number, c.profile_id, p.name 
        FROM channels c
        LEFT JOIN profiles p ON c.profile_id = p.id
    """).fetchall()
    for r in c_rows:
        channels[r['channel_number']] = {'id': r['profile_id'], 'name': r['name']}

    all_files = conn.execute("SELECT * FROM audio_files ORDER BY filename").fetchall()

    # Check published status for active profile
    is_published = False
    if active_profile_id and _column_exists(conn, 'profiles', 'published'):
        pub_row = conn.execute(
            "SELECT published FROM profiles WHERE id = ?", (active_profile_id,)
        ).fetchone()
        if pub_row:
            is_published = bool(pub_row['published'])

    conn.close()

    return render_template('index.html',
                           profiles=profiles,
                           active_profile_id=int(active_profile_id) if active_profile_id else None,
                           mappings=mappings,
                           all_files=all_files,
                           channels=channels,
                           is_published=is_published)

@app.route('/api/profile/create', methods=['POST'])
def create_profile():
    name = request.form.get('name')
    if not name: return jsonify({'ok': False, 'error': 'Name required'}), 400
    try:
        pid = execute_db("INSERT INTO profiles (name) VALUES (?)", (name,))
        return jsonify({'ok': True, 'id': pid})
    except sqlite3.IntegrityError:
        return jsonify({'ok': False, 'error': 'Name exists'}), 400

@app.route('/api/profile/update_instructions', methods=['POST'])
def update_profile_instructions():
    pid = request.form.get('id')
    instr = request.form.get('instructions')
    if not pid: return jsonify({'ok': False, 'error': 'ID required'}), 400
    conn = get_db()
    conn.execute("UPDATE profiles SET instructions = ? WHERE id = ?", (instr, pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/profile/rename', methods=['POST'])
def rename_profile():
    pid = request.form.get('id')
    name = request.form.get('name')
    if not pid or not name: return jsonify({'ok': False, 'error': 'Missing args'}), 400
    try:
        conn = get_db()
        conn.execute("UPDATE profiles SET name = ? WHERE id = ?", (name, pid))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/profile/delete', methods=['POST'])
def delete_profile():
    pid = request.form.get('id')
    if not pid: return jsonify({'ok': False, 'error': 'ID required'}), 400
    conn = get_db()
    conn.execute("DELETE FROM profiles WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/assign', methods=['POST'])
def assign_button():
    pid = request.form.get('profile_id')
    btn = request.form.get('button_id')
    aid = request.form.get('audio_id') 
    if not pid or not btn: return jsonify({'ok': False, 'error': 'Missing args'}), 400
    conn = get_db()
    if not aid:
        conn.execute("DELETE FROM button_mappings WHERE profile_id = ? AND button_id = ?", (pid, btn))
    else:
        conn.execute("INSERT OR REPLACE INTO button_mappings (profile_id, button_id, audio_file_id) VALUES (?, ?, ?)", (pid, btn, aid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/channel/assign', methods=['POST'])
def assign_channel():
    chn = request.form.get('channel')
    pid = request.form.get('profile_id')
    if not chn or not pid: return jsonify({'ok': False, 'error': 'Missing args'}), 400
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO channels (channel_number, profile_id) VALUES (?, ?)", (chn, pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/audio/delete', methods=['POST'])
def delete_audio():
    data = request.json if request.is_json else request.form
    ids = data.get('ids')
    # Handle list passed as form data or json
    if not ids:
        return jsonify({'ok': False, 'error': 'No IDs provided'}), 400
    
    # If form data list
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except:
            ids = [ids]
            
    if not isinstance(ids, list):
        ids = [ids]

    conn = get_db()
    deleted_count = 0
    errors = []
    
    for aid in ids:
        try:
            aid = int(aid)
            row = conn.execute("SELECT filepath, filename FROM audio_files WHERE id = ?", (aid,)).fetchone()
            if row:
                filepath = Path(row['filepath'])
                filename = row['filename']
                # Try to delete file
                try:
                    if filepath.exists():
                        filepath.unlink()
                except Exception as e:
                    errors.append(f"Failed to delete {filename}: {e}")
                    # We continue to delete from DB? 
                    # Probably better to only delete from DB if file is gone or wasn't there.
                    # If file deletion fails (permissions?), we might want to keep DB record.
                    # But if user wants it gone... let's proceed with DB deletion so it's gone from UI.
                
                # Remove from DB
                conn.execute("DELETE FROM audio_files WHERE id = ?", (aid,))
                # Also remove mappings - ON DELETE CASCADE might handle this if set up, 
                # but let's be explicit just in case
                conn.execute("DELETE FROM button_mappings WHERE audio_file_id = ?", (aid,))
                deleted_count += 1
        except Exception as e:
            errors.append(f"Error processing ID {aid}: {e}")
    
    conn.commit()
    conn.close()
    
    return jsonify({'ok': True, 'deleted': deleted_count, 'errors': errors})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'ok': False, 'error': 'No file'}), 400
    files = request.files.getlist('file')
    auto_assign_start = request.form.get('auto_assign_start')
    profile_id = request.form.get('profile_id')
    saved_ids = []
    conn = get_db()
    assign_idx = int(auto_assign_start) if auto_assign_start else None
    
    for f in files:
        if not f or not f.filename: continue
        name = secure_filename(f.filename)
        if not name.lower().endswith('.wav'): continue
        dest_dir = SOUNDS_ROOT / 'uploads'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        # Overwrite behavior: do not rename if exists
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            tmp_path = Path(tmp.name)
            f.save(str(tmp_path))
        try:
            if needs_conversion(tmp_path):
                convert_wav(tmp_path, dest)
            else:
                shutil.move(str(tmp_path), str(dest))
            os.chmod(str(dest), 0o644)
            
            # Update DB - check if exists first to preserve ID (and mappings)
            row = conn.execute("SELECT id FROM audio_files WHERE filepath = ?", (str(dest.resolve()),)).fetchone()
            if row:
                fid = row['id']
            else:
                cursor = conn.execute("INSERT INTO audio_files (filename, filepath) VALUES (?, ?)", (name, str(dest.resolve())))
                fid = cursor.lastrowid
                
            saved_ids.append(fid)
            if assign_idx and profile_id and assign_idx <= 16:
                conn.execute("INSERT OR REPLACE INTO button_mappings (profile_id, button_id, audio_file_id) VALUES (?, ?, ?)", 
                             (profile_id, assign_idx, fid))
                assign_idx += 1
        except Exception as e:
            print(f"Upload error {name}: {e}")
        finally:
            if tmp_path.exists(): tmp_path.unlink()
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'count': len(saved_ids)})

@app.route('/api/metadata/update', methods=['POST'])
def update_metadata():
    aid = request.form.get('id')
    desc = request.form.get('description')
    cat = request.form.get('category')
    hint = request.form.get('hint')
    if not aid: return jsonify({'ok': False}), 400
    conn = get_db()
    conn.execute("UPDATE audio_files SET description = ?, category = ?, hint = ? WHERE id = ?", (desc, cat, hint, aid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

def get_profile_full_data(conn, profile_id):
    profile = conn.execute("""
        SELECT p.*, c.channel_number
        FROM profiles p
        LEFT JOIN channels c ON p.id = c.profile_id
        WHERE p.id = ?
    """, (profile_id,)).fetchone()
    
    rows = conn.execute("""
        SELECT bm.button_id, af.filename, af.description, af.category, af.hint
        FROM button_mappings bm
        JOIN audio_files af ON bm.audio_file_id = af.id
        WHERE bm.profile_id = ?
        ORDER BY bm.button_id ASC
    """, (profile_id,)).fetchall()
    
    # Create mapping for grid view
    mapping = {}
    for r in rows:
        mapping[r['button_id']] = dict(r)
        
    return profile, rows, mapping

@app.route('/print_key/<int:profile_id>')
def print_key(profile_id):
    conn = get_db()
    p, r, m = get_profile_full_data(conn, profile_id)
    conn.close()
    return render_template('print_key.html', items=[{'profile': p, 'rows': r, 'map': m}])

@app.route('/print_key/assigned')
def print_key_assigned():
    conn = get_db()
    items = []
    # Get assigned profiles ordered by channel
    assigned = conn.execute("SELECT profile_id FROM channels WHERE channel_number BETWEEN 1 AND 4 ORDER BY channel_number").fetchall()
    for row in assigned:
        if row['profile_id']:
            p, r, m = get_profile_full_data(conn, row['profile_id'])
            items.append({'profile': p, 'rows': r, 'map': m})
    conn.close()
    return render_template('print_key.html', items=items)

@app.route('/print_tracks')
def print_tracks():
    conn = get_db()
    channels = {}
    c_rows = conn.execute("""
        SELECT c.channel_number, c.profile_id, p.name 
        FROM channels c
        LEFT JOIN profiles p ON c.profile_id = p.id
    """).fetchall()
    conn.close()
    
    for r in c_rows:
        channels[r['channel_number']] = {'id': r['profile_id'], 'name': r['name']}
        
    return render_template('print_tracks.html', channels=channels)

@app.route('/print_worksheet/<int:profile_id>')
def print_worksheet(profile_id):
    conn = get_db()
    p, r, m = get_profile_full_data(conn, profile_id)
    conn.close()
    return render_template('print_worksheet.html', items=[{'profile': p, 'rows': r, 'map': m}])

@app.route('/print_worksheet/assigned')
def print_worksheet_assigned():
    conn = get_db()
    items = []
    assigned = conn.execute("SELECT profile_id FROM channels WHERE channel_number BETWEEN 1 AND 4 ORDER BY channel_number").fetchall()
    for row in assigned:
        if row['profile_id']:
            p, r, m = get_profile_full_data(conn, row['profile_id'])
            items.append({'profile': p, 'rows': r, 'map': m})
    conn.close()
    return render_template('print_worksheet.html', items=items)

# ---------------- TrackPack Export API ----------------

def _table_exists(conn, table_name):
    """Check if a table exists in the database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None

def _column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        return column_name in columns
    except:
        return False

def _get_trackpack_data(conn, track_id):
    """Get trackpack data for a given profile/track ID."""
    has_profiles = _table_exists(conn, 'profiles')

    name = f"Track {track_id}"
    instructions = ""

    if has_profiles:
        profile = conn.execute(
            "SELECT name, instructions FROM profiles WHERE id = ?",
            (track_id,)
        ).fetchone()
        if profile:
            name = profile['name'] or name
            instructions = profile['instructions'] or ""

    # Check which columns exist in audio_files
    has_description = _column_exists(conn, 'audio_files', 'description')
    has_hint = _column_exists(conn, 'audio_files', 'hint')
    has_category = _column_exists(conn, 'audio_files', 'category')

    # Build SELECT clause based on available columns
    select_cols = ["bm.button_id", "af.filename", "af.filepath"]
    if has_description:
        select_cols.append("af.description")
    if has_hint:
        select_cols.append("af.hint")
    if has_category:
        select_cols.append("af.category")

    query = f"""
        SELECT {', '.join(select_cols)}
        FROM button_mappings bm
        JOIN audio_files af ON bm.audio_file_id = af.id
        WHERE bm.profile_id = ?
        ORDER BY bm.button_id ASC
    """

    rows = conn.execute(query, (track_id,)).fetchall()

    buttons = []
    for row in rows:
        btn = {
            "button": row['button_id'],
            "filename": row['filename'],
            "filepath": row['filepath'],
            "answer": (row['description'] if has_description else "") or "",
            "hint": (row['hint'] if has_hint else "") or "",
            "category": (row['category'] if has_category else "") or ""
        }
        buttons.append(btn)

    return {
        "id": track_id,
        "name": name,
        "instructions": instructions,
        "buttons": buttons
    }

def _compute_trackpack_hash(data, adapter=None):
    """Compute a revision hash based on DB mapping + audio file mtimes/sizes.

    Args:
        data: Trackpack data dict from _get_trackpack_data()
        adapter: Storage adapter (uses default if not provided)

    Returns:
        16-character hex hash string
    """
    if adapter is None:
        adapter = get_storage_adapter()

    hasher = hashlib.sha256()

    # Include track metadata
    hasher.update(f"{data['id']}:{data['name']}:{data['instructions']}".encode('utf-8'))

    # Include button mappings and file stats (via storage adapter)
    for btn in data['buttons']:
        hasher.update(f"{btn['button']}:{btn['filename']}:{btn['answer']}:{btn['hint']}:{btn['category']}".encode('utf-8'))

        meta = adapter.get_file_metadata(btn['filepath'])
        if meta:
            hasher.update(f":{meta.mtime}:{meta.size}".encode('utf-8'))

    return hasher.hexdigest()[:16]


def _get_trackpack_updated_at(data, db_updated_at=None, db_created_at=None, adapter=None):
    """Get the most recent modification time for a trackpack.

    Delegates to storage module's get_trackpack_updated_at() for consistent
    timestamp logic across the codebase.

    Priority:
    1. db_updated_at if valid
    2. max(mtime) of audio files (via adapter)
    3. db_created_at if valid
    4. Current time as last resort

    Note: mtime is checked before created_at because older MSS schemas lack
    updated_at, but file mtimes still reflect actual content changes.

    Args:
        data: Trackpack data dict with 'buttons' containing file paths
        db_updated_at: Optional updated_at from DB (ISO8601 or SQLite format)
        db_created_at: Optional created_at from DB (ISO8601 or SQLite format)
        adapter: Storage adapter (uses default if not provided)

    Returns:
        ISO 8601 timestamp string (UTC), e.g. "2026-01-31T18:42:10Z"
    """
    return storage_get_updated_at(
        data,
        db_updated_at=db_updated_at,
        db_created_at=db_created_at,
        adapter=adapter
    )


def _make_stable_id(track_id):
    """Generate a stable identifier that won't change even if display_name changes."""
    return f"trackpack-{track_id}"

@app.route('/api/trackpacks')
def api_trackpacks():
    """List available trackpacks (profiles) with versioning metadata.

    Response includes:
    - id: numeric database ID (for URL compatibility)
    - name: human-readable name (existing field, preserved for compatibility)
    - instructions: profile instructions text (existing field)
    - stable_id: immutable identifier (e.g., "trackpack-13")
    - revision: content hash that changes when audio/hints/answers/mapping change
    - updated_at: ISO timestamp of most recent content change
    """
    conn = get_db()
    try:
        has_profiles = _table_exists(conn, 'profiles')

        # Check for timestamp columns in profiles table
        has_updated_at = has_profiles and _column_exists(conn, 'profiles', 'updated_at')
        has_modified_at = has_profiles and _column_exists(conn, 'profiles', 'modified_at')
        has_created_at = has_profiles and _column_exists(conn, 'profiles', 'created_at')

        has_published = has_profiles and _column_exists(conn, 'profiles', 'published')

        if has_profiles:
            # Build query with optional timestamp columns
            select_cols = "id, name, instructions"
            if has_updated_at:
                select_cols += ", updated_at"
            elif has_modified_at:
                select_cols += ", modified_at"
            if has_created_at:
                select_cols += ", created_at"
            where_clause = " WHERE published = 1" if has_published else ""
            rows = conn.execute(
                f"SELECT {select_cols} FROM profiles{where_clause} ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT profile_id as id FROM button_mappings ORDER BY profile_id"
            ).fetchall()

        trackpacks = []
        for row in rows:
            track_id = row['id'] if has_profiles else row['id']

            # Compute revision and updated_at with error handling
            revision = None
            updated_at = None
            name = row['name'] if has_profiles and row['name'] else f"Track {track_id}"
            instructions = row['instructions'] if has_profiles and row['instructions'] else ""

            # Get DB timestamps if available
            db_updated_at = None
            db_created_at = None
            if has_updated_at:
                db_updated_at = row['updated_at']
            elif has_modified_at:
                db_updated_at = row['modified_at']
            if has_created_at:
                db_created_at = row['created_at']

            try:
                data = _get_trackpack_data(conn, track_id)
                adapter = get_storage_adapter()
                revision = _compute_trackpack_hash(data, adapter=adapter)
                updated_at = _get_trackpack_updated_at(
                    data,
                    db_updated_at=db_updated_at,
                    db_created_at=db_created_at,
                    adapter=adapter
                )
                name = data['name']
                instructions = data['instructions']
            except Exception as e:
                print(f"[MSS] Failed to compute revision for trackpack {track_id}: {e}")

            trackpacks.append({
                "id": track_id,
                "name": name,
                "instructions": instructions,
                "stable_id": _make_stable_id(track_id),
                "revision": revision,
                "updated_at": updated_at
            })

        return jsonify({"ok": True, "trackpacks": trackpacks})
    finally:
        conn.close()

@app.route('/api/trackpacks/<int:track_id>/manifest.json')
def api_trackpack_manifest(track_id):
    """Return TrackPack v1 manifest JSON with versioning metadata.

    The manifest includes stable_id and revision for mobile app sync.
    The revision here will match the revision embedded in the zip file.
    """
    conn = get_db()
    try:
        data = _get_trackpack_data(conn, track_id)

        # Check if track exists (has buttons or profile)
        has_profiles = _table_exists(conn, 'profiles')
        if has_profiles:
            profile = conn.execute(
                "SELECT id FROM profiles WHERE id = ?", (track_id,)
            ).fetchone()
            if not profile and not data['buttons']:
                return jsonify({"ok": False, "error": "Track not found"}), 404
        elif not data['buttons']:
            return jsonify({"ok": False, "error": "Track not found"}), 404

        adapter = get_storage_adapter()
        revision = _compute_trackpack_hash(data, adapter=adapter)
        stable_id = _make_stable_id(track_id)

        manifest = {
            "format": "mss-trackpack",
            "version": 1,
            "stable_id": stable_id,
            "revision": revision,
            "track": {
                "id": data['id'],
                "name": data['name'],
                "instructions": data['instructions']
            },
            "buttons": [
                {
                    "button": btn['button'],
                    "filename": btn['filename'],
                    "answer": btn['answer'],
                    "hint": btn['hint'],
                    "category": btn['category']
                }
                for btn in data['buttons']
            ]
        }

        return jsonify(manifest)
    finally:
        conn.close()

@app.route('/api/trackpacks/<int:track_id>.zip')
def api_trackpack_zip(track_id):
    """Build and serve trackpack as a revision-addressed zip file with caching.

    Zip filename format: {stable_id}_{revision}.zip (e.g., trackpack-13_a94c3e1f.zip)
    This ensures zips are never ambiguous - each revision gets a unique filename.

    Old zip revisions for this trackpack are cleaned up before creating a new one.
    The manifest inside the zip includes stable_id and revision for verification.
    """
    conn = get_db()
    try:
        data = _get_trackpack_data(conn, track_id)

        # Check if track exists
        has_profiles = _table_exists(conn, 'profiles')
        if has_profiles:
            profile = conn.execute(
                "SELECT id FROM profiles WHERE id = ?", (track_id,)
            ).fetchone()
            if not profile and not data['buttons']:
                return jsonify({"ok": False, "error": "Track not found"}), 404
        elif not data['buttons']:
            return jsonify({"ok": False, "error": "Track not found"}), 404

        # Get storage adapter for file operations
        adapter = get_storage_adapter()

        # Compute revision hash and stable_id
        revision = _compute_trackpack_hash(data, adapter=adapter)
        stable_id = _make_stable_id(track_id)

        # Ensure exports directory exists
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # Revision-addressed zip filename: {stable_id}_{revision}.zip
        zip_filename = f"{stable_id}_{revision}.zip"
        zip_path = EXPORTS_DIR / zip_filename

        if not zip_path.exists():
            # Clean up old versions of this trackpack (any revision)
            # Match both old format (trackpack_{id}_*.zip) and new format ({stable_id}_*.zip)
            cleanup_patterns = [
                f"trackpack_{track_id}_*.zip",  # Legacy format
                f"{stable_id}_*.zip"            # New format
            ]
            for pattern in cleanup_patterns:
                for old_zip in EXPORTS_DIR.glob(pattern):
                    if old_zip != zip_path:  # Don't delete the one we're about to create
                        try:
                            old_zip.unlink()
                        except OSError:
                            # Log but don't fail - disk may be read-only or file locked
                            pass

            # Build the zip atomically: write to temp file, then rename
            # This prevents serving partial zips if process is interrupted
            temp_zip_path = EXPORTS_DIR / f".tmp_{zip_filename}"
            try:
                with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    manifest = {
                        "format": "mss-trackpack",
                        "version": 1,
                        "stable_id": stable_id,
                        "revision": revision,
                        "track": {
                            "id": data['id'],
                            "name": data['name'],
                            "instructions": data['instructions']
                        },
                        "buttons": [
                            {
                                "button": btn['button'],
                                "filename": btn['filename'],
                                "answer": btn['answer'],
                                "hint": btn['hint'],
                                "category": btn['category']
                            }
                            for btn in data['buttons']
                        ]
                    }
                    zf.writestr('manifest.json', json.dumps(manifest, indent=2))

                    # Add audio files (read through storage adapter)
                    for btn in data['buttons']:
                        file_bytes = adapter.read_file_bytes(btn['filepath'])
                        if file_bytes is not None:
                            zf.writestr(f"audio/{btn['filename']}", file_bytes)

                # Atomic rename (on POSIX systems)
                temp_zip_path.rename(zip_path)
            except Exception:
                # Clean up temp file on failure
                if temp_zip_path.exists():
                    try:
                        temp_zip_path.unlink()
                    except OSError:
                        pass
                raise

        # Serve the zip with human-readable download name
        safe_name = data['name'].replace(' ', '_').replace('/', '_')[:50]
        download_name = f"{safe_name}.zip"

        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=download_name
        )
    finally:
        conn.close()

# ---------------- Publish API ----------------

@app.route('/api/push/publish', methods=['POST'])
def publish_track():
    """Mark a track as published. Push notification is sent by the browser."""
    data = request.json if request.is_json else request.form
    profile_id = data.get('profile_id')
    if not profile_id:
        return jsonify({'ok': False, 'error': 'profile_id required'}), 400

    conn = get_db()
    try:
        profile = conn.execute(
            "SELECT id, name FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if not profile:
            return jsonify({'ok': False, 'error': 'Profile not found'}), 404

        conn.execute(
            "UPDATE profiles SET published = 1 WHERE id = ?", (profile_id,)
        )
        conn.commit()

        return jsonify({'ok': True, 'profile_id': profile['id'], 'name': profile['name']})
    finally:
        conn.close()

@app.route('/api/push/unpublish', methods=['POST'])
def unpublish_track():
    """Mark a track as unpublished (hidden from mobile app listing)."""
    data = request.json if request.is_json else request.form
    profile_id = data.get('profile_id')
    if not profile_id:
        return jsonify({'ok': False, 'error': 'profile_id required'}), 400

    conn = get_db()
    try:
        profile = conn.execute(
            "SELECT id, name FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if not profile:
            return jsonify({'ok': False, 'error': 'Profile not found'}), 404

        conn.execute(
            "UPDATE profiles SET published = 0 WHERE id = ?", (profile_id,)
        )
        conn.commit()
        return jsonify({'ok': True, 'profile_id': profile['id'], 'name': profile['name']})
    finally:
        conn.close()

# ---------------- Server Identity API ----------------

@app.route('/api/server-info')
def api_server_info():
    """Return server identity and capabilities.

    Provides stable identification for this MSS instance, useful for:
    - Client pairing and recognition
    - Multi-device coordination
    - Future cloud sync features

    The server_id is persistent across restarts and reboots.
    """
    return jsonify({
        "ok": True,
        "server_id": get_server_id(DATA_DIR),
        "server_name": get_server_name(DATA_DIR),
        "server_type": "local",
        "api_version": "v1",
        "capabilities": {
            "trackpacks": True,
            "updates": True,
            "cloud_ready": True
        }
    })

# ---------------- Network Routes ----------------

@app.route('/wifi')
def wifi_page():
    nets = nu.wifi_scan()
    wcfg = nu.wifi_load_config()
    return render_template('wifi.html', nets=nets, wcfg=wcfg)

@app.route('/bt')
def bt_page():
    devices = nu.bt_scan()
    paired = nu.bt_paired()
    for p in paired: p['connected'] = nu.bt_is_connected(p['mac'])
    bcfg = nu.bt_load_config()
    return render_template('bt.html', devices=devices, paired=paired, bcfg=bcfg)

@app.route('/bt/paired')
def bt_paired_api():
    items = nu.bt_paired()
    for p in items: p['connected'] = nu.bt_is_connected(p['mac'])
    return jsonify({'ok': True, 'paired': items})

@app.post('/wifi/connect')
def wifi_connect_route():
    data = request.json if request.is_json else request.form
    ssid = data.get('ssid')
    password = data.get('password', '')
    if not ssid: return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    out = nu.wifi_connect(ssid, password)
    return jsonify({'ok': True, 'output': out})

@app.post('/wifi/remember')
def wifi_remember():
    data = request.json if request.is_json else request.form
    ssid = data.get('ssid')
    password = data.get('password', '')
    if not ssid: return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    cfg = nu.wifi_load_config()
    cfg.setdefault('known', {})[ssid] = cfg['known'].get(ssid, {"password":"", "auto": False, "priority": 0})
    cfg['known'][ssid]['password'] = password
    nu.wifi_save_config(cfg)
    return jsonify({'ok': True})

@app.post('/wifi/forget')
def wifi_forget_route():
    data = request.json if request.is_json else request.form
    ssid = data.get('ssid')
    if not ssid: return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    out = nu.wifi_forget(ssid)
    cfg = nu.wifi_load_config()
    if cfg.get('known', {}).pop(ssid, None) is not None:
        nu.wifi_save_config(cfg)
    return jsonify({'ok': True, 'output': out})

@app.post('/wifi/auto')
def wifi_auto_toggle():
    payload = request.json if request.is_json else request.form
    ssid = payload.get('ssid')
    enable = payload.get('enable')
    priority = payload.get('priority')
    if ssid:
        try: prio = int(priority if priority is not None else 0)
        except: prio = 0
        en = str(enable).lower() in ('1','true','yes','on')
        cfg = nu.wifi_load_config()
        cfg.setdefault('known', {})[ssid] = cfg['known'].get(ssid, {"password":"", "auto": False, "priority": 0})
        cfg['known'][ssid]['auto'] = en
        cfg['known'][ssid]['priority'] = prio
        nu.wifi_save_config(cfg)
        nm_out = nu.wifi_set_autopref(ssid, en, prio)
        return jsonify({'ok': True, 'ssid': ssid, 'auto': en, 'priority': prio, 'nm': nm_out})
    else:
        en = str(enable).lower() in ('1', 'true', 'yes', 'on') if enable is not None else False
        cfg = nu.wifi_load_config()
        cfg['autoConnect'] = en
        nu.wifi_save_config(cfg)
        return jsonify({'ok': True, 'autoConnect': en})

@app.post('/bt/connect')
def bt_connect_route():
    data = request.json if request.is_json else request.form
    mac = data.get('mac')
    if not mac: return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    out = nu.bt_connect_sync(mac)
    sink_status = nu.bt_set_default_sink(mac)
    return jsonify({'ok': True, 'output': out, 'sink': sink_status})

@app.post('/bt/connect_start')
def bt_connect_start():
    data = request.json if request.is_json else request.form
    mac = data.get('mac')
    if not mac: return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    if nu.start_bt_connect_thread(mac):
        return jsonify({'ok': True, 'running': True, 'mac': mac})
    return jsonify({'ok': True, 'running': False, 'error': 'Job busy'})

@app.get('/bt/status')
def bt_status():
    items = nu.bt_paired()
    for p in items: p['connected'] = nu.bt_is_connected(p['mac'])
    try:
        with (APP_ROOT / 'log' / 'bt_connect.log').open('r', encoding='utf-8') as f:
            data = f.read()
            transcript = data[-5000:]
    except: transcript = ''
    try:
        info = subprocess.check_output(['pactl', 'info'], text=True)
        default_sink = next((ln.split(':',1)[1].strip() for ln in info.splitlines() if ln.startswith('Default Sink:')), '')
    except: default_sink = ''
    return jsonify({'ok': True, 'paired': items, 'default_sink': default_sink, 'transcript': transcript})

@app.post('/bt/remember')
def bt_remember():
    data = request.json if request.is_json else request.form
    mac = data.get('mac')
    name = data.get('name', '')
    make_default = str(data.get('default', '')).lower() in ('1','true','yes','on')
    if not mac: return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    cfg = nu.bt_load_config()
    cfg.setdefault('known', {})[mac] = {"name": name}
    if make_default: cfg['default'] = mac
    nu.bt_save_config(cfg)
    return jsonify({'ok': True})

@app.post('/bt/forget')
def bt_forget_route():
    data = request.json if request.is_json else request.form
    mac = data.get('mac')
    if not mac: return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    out = nu.bt_forget(mac)
    cfg = nu.bt_load_config()
    if cfg.get('known', {}).pop(mac, None) is not None:
        if cfg.get('default') == mac: cfg['default'] = ''
        nu.bt_save_config(cfg)
    return jsonify({'ok': True, 'output': out})

@app.get('/audio/<int:button_id>')
def serve_audio(button_id: int):
    """Serve audio file for browser playback."""
    conn = get_db()
    try:
        profile_id_str = request.args.get('profile_id')
        profile_id = None

        if profile_id_str:
            try:
                profile_id = int(profile_id_str)
            except (ValueError, TypeError):
                return jsonify({'ok': False, 'error': 'Invalid profile_id'}), 400

        if not profile_id:
            chn = get_system_config('active_channel', '1')
            try:
                chn = int(chn)
            except (ValueError, TypeError):
                chn = 1
            row = conn.execute(
                "SELECT profile_id FROM channels WHERE channel_number = ?", (chn,)
            ).fetchone()
            profile_id = row['profile_id'] if row else None

        if not profile_id:
            return jsonify({'ok': False, 'error': 'No profile found'}), 400

        row = conn.execute("""
            SELECT af.filepath, af.filename
            FROM button_mappings bm
            JOIN audio_files af ON bm.audio_file_id = af.id
            WHERE bm.profile_id = ? AND bm.button_id = ?
        """, (profile_id, button_id)).fetchone()

        if not row:
            return jsonify({'ok': False, 'error': f'No audio mapped to button {button_id}'}), 404

        path = row['filepath']
        if not path or not os.path.exists(path):
            return jsonify({'ok': False, 'error': 'Audio file not found on disk'}), 404

        return send_file(path, mimetype='audio/wav')
    finally:
        conn.close()

@app.post('/play/<int:button_id>')
def play(button_id: int):
    """Play audio for a button. Uses profile_id from query param or active channel."""
    conn = get_db()
    
    try:
        # Get profile_id from query param (as string) and convert to int
        profile_id_str = request.args.get('profile_id')
        profile_id = None
        
        if profile_id_str:
            try:
                profile_id = int(profile_id_str)
            except (ValueError, TypeError):
                conn.close()
                return jsonify({'ok': False, 'error': 'Invalid profile_id'}), 400
        
        if not profile_id:
            # Fallback to hardware active channel
            chn = get_system_config('active_channel', '1')
            try:
                chn = int(chn)
            except (ValueError, TypeError):
                chn = 1
            row = conn.execute("SELECT profile_id FROM channels WHERE channel_number = ?", (chn,)).fetchone()
            profile_id = row['profile_id'] if row else None
            
        if not profile_id:
            conn.close()
            return jsonify({'ok': False, 'error': 'No profile found for button'}), 400
            
        # Query for the audio file
        row = conn.execute("""
            SELECT af.filepath, af.filename
            FROM button_mappings bm
            JOIN audio_files af ON bm.audio_file_id = af.id
            WHERE bm.profile_id = ? AND bm.button_id = ?
        """, (profile_id, button_id)).fetchone()
        
        if not row:
            conn.close()
            return jsonify({'ok': False, 'error': f'No audio file mapped to button {button_id}'}), 400
            
        path = row['filepath']
        filename = row['filename']
        
        if not path or not os.path.exists(path):
            conn.close()
            return jsonify({'ok': False, 'error': f'Audio file not found: {filename}'}), 400
            
        # Get audio device and play
        aplay_device = get_system_config('aplayDevice', 'default')
        cmd = ['aplay', '-q', '-D', str(aplay_device), str(path)]
        
        # Check if aplay exists
        if not shutil.which('aplay'):
            conn.close()
            return jsonify({'ok': False, 'error': 'aplay command not found'}), 500
        
        # Run aplay and capture any immediate errors
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Give it a moment to start and check for immediate errors
            time.sleep(0.1)
            if process.poll() is not None:
                # Process exited immediately (error)
                stdout, stderr = process.communicate()
                error_msg = stderr.strip() or stdout.strip() or 'aplay failed to start'
                return jsonify({'ok': False, 'error': f'aplay error: {error_msg}'}), 500
            
            return jsonify({'ok': True, 'filename': filename})
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Failed to play audio: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Unexpected error: {str(e)}'}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
