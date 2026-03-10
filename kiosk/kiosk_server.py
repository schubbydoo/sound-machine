#!/usr/bin/env python3
"""
Memory Spark Station - Kiosk Server
Sidecar service: serves touchscreen UI on port 8081.
Monitors soundtrigger journal for last-pressed button.
Zero modifications to existing sound-machine services.
"""
import io
import json
import re
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

try:
    from flask import Flask, render_template, jsonify, request
except ImportError:
    print("Flask not found. Use the sound-machine venv.", file=sys.stderr)
    sys.exit(1)

DB_PATH    = Path('/home/soundconsole/sound-machine/data/sound_machine.db')
SOUNDS_DIR = Path('/home/soundconsole/sound-machine/Sounds/uploads')
CLOUD_URL  = 'https://api.memorysparkplay.fun'

app = Flask(__name__)

# Shared state protected by lock
_state = {'last_button': None}
_lock  = threading.Lock()


# ── DB helpers ──────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql, args=()):
    conn = _db()
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def _execute(sql, args=()):
    conn = _db()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_config(key, default=None):
    rows = _query("SELECT value FROM system_config WHERE key = ?", (key,))
    return rows[0]['value'] if rows else default


def set_config(key, value):
    _execute(
        "INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)",
        (key, str(value))
    )


# ── Active profile (replaces channel system) ────────────────────────────────

def get_active_profile_id():
    val = get_config('active_profile_id')
    if val:
        pid = int(val)
        # Verify profile still exists (may have been deleted via webUI)
        if _query("SELECT id FROM profiles WHERE id=?", (pid,)):
            return pid
    # Fall back to first playlist entry
    rows = _query(
        "SELECT id FROM profiles WHERE in_playlist=1 ORDER BY playlist_order LIMIT 1"
    )
    if rows:
        pid = rows[0]['id']
        set_active_profile(pid)
        return pid
    return None


def set_active_profile(profile_id):
    """Set the active profile. Bridge: keeps channel 1 in sync for soundtrigger.py."""
    set_config('active_profile_id', str(profile_id))
    # Bridge — soundtrigger.py reads active_channel → channels table → profile_id
    conn = _db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO channels (channel_number, profile_id) VALUES (1, ?)",
            (profile_id,)
        )
        conn.commit()
    finally:
        conn.close()
    set_config('active_channel', '1')


# ── Playlist helpers ─────────────────────────────────────────────────────────

def get_playlist():
    rows = _query("""
        SELECT id, name, instructions, playlist_order
        FROM profiles
        WHERE in_playlist = 1
        ORDER BY playlist_order
    """)
    # Renumber sequentially so webUI deletions don't leave gaps (1,3,4 → 1,2,3)
    result = []
    for seq, r in enumerate(rows, start=1):
        if r['playlist_order'] != seq:
            _execute(
                "UPDATE profiles SET playlist_order=? WHERE id=?",
                (seq, r['id'])
            )
        result.append({
            'id':          r['id'],
            'name':        r['name'],
            'instruction': r['instructions'] or '',
            'order':       seq,
        })
    return result


def get_button_data(profile_id, button_id):
    if not profile_id or not button_id:
        return {'hint': None, 'answer': None}
    rows = _query("""
        SELECT a.description, a.hint
        FROM button_mappings bm
        JOIN audio_files a ON bm.audio_file_id = a.id
        WHERE bm.profile_id = ? AND bm.button_id = ?
    """, (profile_id, button_id))
    if not rows:
        return {'hint': None, 'answer': None}
    r = rows[0]
    return {'hint': r['hint'] or None, 'answer': r['description'] or None}


# ── Cloud helpers ────────────────────────────────────────────────────────────

def _cloud_url():
    return get_config('cloud_server_url', CLOUD_URL).rstrip('/')


def _fetch_cloud_trackpacks(timeout=8):
    """Fetch trackpack list from cloud. Returns list or raises."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        f"{_cloud_url()}/api/trackpacks",
        headers={'User-Agent': 'MSS-Kiosk/1.0', 'Accept': 'application/json'}
    )
    resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    data = json.loads(resp.read())
    trackpacks = data if isinstance(data, list) else data.get('trackpacks', [])
    _sync_cloud_stable_ids(trackpacks)
    return trackpacks


def _sync_cloud_stable_ids(trackpacks):
    """Auto-link local profiles to cloud trackpacks by name when stable_id is missing.

    Runs every time we have fresh cloud data. Safe: only fills in NULL entries,
    never overwrites an existing stable_id. Tracks that are re-downloaded via the
    library already have their stable_id set by the download route.
    """
    if not trackpacks:
        return
    try:
        cloud_by_name = {t['name'].strip().lower(): t for t in trackpacks}
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT id, name FROM profiles WHERE cloud_stable_id IS NULL OR cloud_stable_id = ''"
            ).fetchall()
            # Convert to plain dicts so Row objects don't rely on an open cursor
            unlinked = [{'id': r['id'], 'name': r['name']} for r in rows]
            updated = 0
            for row in unlinked:
                match = cloud_by_name.get(row['name'].strip().lower())
                if match:
                    conn.execute(
                        "UPDATE profiles SET cloud_stable_id=? WHERE id=?",
                        (match['stable_id'], row['id'])
                    )
                    updated += 1
            if updated:
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[sync_cloud_ids] warning: {e}", flush=True)


# ── Play surface routes ──────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('kiosk.html')


@app.route('/api/state')
def api_state():
    profile_id = get_active_profile_id()
    playlist   = get_playlist()

    with _lock:
        last_button = _state['last_button']

    button_data = get_button_data(profile_id, last_button)

    rows = _query("SELECT instructions FROM profiles WHERE id = ?", (profile_id,)) \
        if profile_id else []
    instruction = rows[0]['instructions'] if rows else ''

    return jsonify({
        'active_profile_id': profile_id,
        'playlist':          playlist,
        'last_button':       last_button,
        'hint':              button_data['hint'],
        'answer':            button_data['answer'],
        'instruction':       instruction or '',
    })


@app.route('/api/profile/select/<int:profile_id>', methods=['POST'])
def api_select_profile(profile_id):
    row = _query("SELECT id FROM profiles WHERE id=?", (profile_id,))
    if not row:
        return jsonify({'ok': False, 'error': 'Profile not found'}), 404
    set_active_profile(profile_id)
    with _lock:
        _state['last_button'] = None
    return jsonify({'ok': True})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    subprocess.run(['pkill', '-x', 'aplay'], capture_output=True)
    return jsonify({'ok': True})


# ── Library routes ───────────────────────────────────────────────────────────

@app.route('/library')
def library():
    return render_template('library.html')


@app.route('/api/library/state')
def api_library_state():
    rows = _query("SELECT COUNT(*) as n FROM profiles WHERE in_playlist=1")
    playlist_count = rows[0]['n'] if rows else 0
    rows = _query("SELECT COUNT(*) as n FROM profiles")
    local_count = rows[0]['n'] if rows else 0
    return jsonify({
        'ok':            True,
        'playlist_count': playlist_count,
        'local_count':    local_count,
    })


@app.route('/api/library/playlist')
def api_library_playlist():
    rows = _query("""
        SELECT id, name, playlist_order, cloud_stable_id, cloud_revision
        FROM profiles WHERE in_playlist=1 ORDER BY playlist_order
    """)

    # Check for updates (best-effort)
    cloud_revisions = {}
    try:
        for tp in _fetch_cloud_trackpacks(timeout=5):
            cloud_revisions[tp['stable_id']] = tp['revision']
    except Exception:
        pass

    result = []
    for seq, r in enumerate(rows, start=1):
        update_available = False
        if r['cloud_stable_id'] and r['cloud_revision']:
            cr = cloud_revisions.get(r['cloud_stable_id'])
            update_available = bool(cr and cr != r['cloud_revision'])
        result.append({
            'id':               r['id'],
            'name':             r['name'],
            'order':            seq,
            'cloud_stable_id':  r['cloud_stable_id'],
            'update_available': update_available,
        })
    return jsonify({'ok': True, 'playlist': result})


@app.route('/api/library/local')
def api_library_local():
    rows = _query("""
        SELECT id, name, in_playlist, playlist_order, source, cloud_stable_id, cloud_revision
        FROM profiles
        ORDER BY COALESCE(in_playlist, 0) DESC, COALESCE(playlist_order, 9999), name
    """)

    cloud_revisions = {}
    try:
        for tp in _fetch_cloud_trackpacks(timeout=5):
            cloud_revisions[tp['stable_id']] = tp['revision']
    except Exception:
        pass

    result = []
    for r in rows:
        update_available = False
        if r['cloud_stable_id'] and r['cloud_revision']:
            cr = cloud_revisions.get(r['cloud_stable_id'])
            update_available = bool(cr and cr != r['cloud_revision'])
        result.append({
            'id':               r['id'],
            'name':             r['name'],
            'in_playlist':      bool(r['in_playlist']),
            'playlist_order':   r['playlist_order'],
            'source':           r['source'] or 'local',
            'cloud_stable_id':  r['cloud_stable_id'],
            'update_available': update_available,
        })
    return jsonify({'ok': True, 'local': result})


@app.route('/api/library/available')
def api_library_available():
    local_rows = _query("SELECT cloud_stable_id, name FROM profiles")
    local_ids   = {r['cloud_stable_id'] for r in local_rows if r['cloud_stable_id']}
    local_names = {r['name'].strip().lower() for r in local_rows}

    try:
        trackpacks = _fetch_cloud_trackpacks(timeout=8)
        # Deduplicate by stable_id, then exclude anything already local by id or name
        seen = set()
        available = []
        for t in trackpacks:
            sid = t['stable_id']
            if sid in seen:
                continue
            seen.add(sid)
            if sid in local_ids:
                continue
            if t.get('name', '').strip().lower() in local_names:
                continue
            available.append(t)
        return jsonify({'ok': True, 'available': available})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'available': []})


@app.route('/api/library/<int:profile_id>/toggle', methods=['POST'])
def api_library_toggle(profile_id):
    rows = _query(
        "SELECT in_playlist, playlist_order FROM profiles WHERE id=?", (profile_id,)
    )
    if not rows:
        return jsonify({'ok': False, 'error': 'Not found'}), 404

    currently_in = bool(rows[0]['in_playlist'])

    if currently_in:
        current_order = rows[0]['playlist_order']
        conn = _db()
        try:
            conn.execute(
                "UPDATE profiles SET in_playlist=0, playlist_order=NULL WHERE id=?",
                (profile_id,)
            )
            conn.execute(
                """UPDATE profiles SET playlist_order = playlist_order - 1
                   WHERE in_playlist=1 AND playlist_order > ?""",
                (current_order,)
            )
            conn.commit()
        finally:
            conn.close()
        # If this was the active profile, switch to first remaining playlist entry
        if str(profile_id) == str(get_config('active_profile_id')):
            first = _query(
                "SELECT id FROM profiles WHERE in_playlist=1 ORDER BY playlist_order LIMIT 1"
            )
            if first:
                set_active_profile(first[0]['id'])
    else:
        max_rows = _query(
            "SELECT MAX(playlist_order) as m FROM profiles WHERE in_playlist=1"
        )
        next_order = (max_rows[0]['m'] or 0) + 1
        _execute(
            "UPDATE profiles SET in_playlist=1, playlist_order=? WHERE id=?",
            (next_order, profile_id)
        )

    return jsonify({'ok': True, 'in_playlist': not currently_in})


@app.route('/api/library/<int:profile_id>/delete', methods=['POST'])
def api_library_delete(profile_id):
    rows = _query(
        "SELECT in_playlist, playlist_order FROM profiles WHERE id=?", (profile_id,)
    )
    if not rows:
        return jsonify({'ok': False, 'error': 'Not found'}), 404

    # If active, switch away first
    if str(profile_id) == str(get_config('active_profile_id')):
        alt = _query(
            "SELECT id FROM profiles WHERE in_playlist=1 AND id!=? ORDER BY playlist_order LIMIT 1",
            (profile_id,)
        )
        if alt:
            set_active_profile(alt[0]['id'])

    current_order = rows[0]['playlist_order']
    conn = _db()
    try:
        conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        if current_order:
            conn.execute(
                """UPDATE profiles SET playlist_order = playlist_order - 1
                   WHERE in_playlist=1 AND playlist_order > ?""",
                (current_order,)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True})


@app.route('/api/library/download/<stable_id>', methods=['POST'])
def api_library_download(stable_id):
    """Download a trackpack from the cloud and install it locally."""
    m = re.match(r'trackpack-(\d+)', stable_id)
    if not m:
        return jsonify({'ok': False, 'error': 'Invalid stable_id'}), 400
    cloud_id = m.group(1)

    try:
        ctx = ssl.create_default_context()

        # Get revision from trackpack list
        trackpacks = _fetch_cloud_trackpacks(timeout=10)
        tp = next((t for t in trackpacks if t['stable_id'] == stable_id), None)
        if not tp:
            return jsonify({'ok': False, 'error': 'Track not found on cloud'}), 404
        revision = tp['revision']

        # Download ZIP
        zip_req = urllib.request.Request(
            f"{_cloud_url()}/api/trackpacks/{cloud_id}.zip",
            headers={'User-Agent': 'MSS-Kiosk/1.0'}
        )
        zip_resp = urllib.request.urlopen(zip_req, timeout=120, context=ctx)
        zip_data = zip_resp.read()

        # Parse ZIP
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            manifest = json.loads(zf.read('manifest.json'))
            track    = manifest['track']
            buttons  = manifest['buttons']

            # Install audio files
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            for btn in buttons:
                arc_path = f"audio/{btn['filename']}"
                if arc_path in zf.namelist():
                    dest = SOUNDS_DIR / btn['filename']
                    if not dest.exists():
                        dest.write_bytes(zf.read(arc_path))

            # Install profile and button mappings
            conn = _db()
            try:
                existing = conn.execute(
                    "SELECT id FROM profiles WHERE name=?", (track['name'],)
                ).fetchone()

                if existing:
                    profile_id = existing['id']
                    conn.execute(
                        """UPDATE profiles
                           SET instructions=?, source='downloaded',
                               cloud_stable_id=?, cloud_revision=?
                           WHERE id=?""",
                        (track['instructions'], stable_id, revision, profile_id)
                    )
                else:
                    cur = conn.execute(
                        """INSERT INTO profiles
                           (name, instructions, source, cloud_stable_id, cloud_revision)
                           VALUES (?, ?, 'downloaded', ?, ?)""",
                        (track['name'], track['instructions'], stable_id, revision)
                    )
                    profile_id = cur.lastrowid

                # Replace button mappings
                conn.execute(
                    "DELETE FROM button_mappings WHERE profile_id=?", (profile_id,)
                )
                for btn in buttons:
                    fname     = btn['filename']
                    filepath  = str(SOUNDS_DIR / fname)
                    audio_row = conn.execute(
                        "SELECT id FROM audio_files WHERE filename=?", (fname,)
                    ).fetchone()
                    if audio_row:
                        audio_id = audio_row['id']
                    else:
                        cur2 = conn.execute(
                            """INSERT INTO audio_files
                               (filename, filepath, description, hint)
                               VALUES (?, ?, ?, ?)""",
                            (fname, filepath,
                             btn.get('answer'), btn.get('hint'))
                        )
                        audio_id = cur2.lastrowid
                    conn.execute(
                        """INSERT OR REPLACE INTO button_mappings
                           (profile_id, button_id, audio_file_id)
                           VALUES (?, ?, ?)""",
                        (profile_id, btn['button'], audio_id)
                    )
                conn.commit()
            finally:
                conn.close()

        return jsonify({'ok': True, 'profile_id': profile_id, 'name': track['name']})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Log file monitor ─────────────────────────────────────────────────────────

LOG_PATH = Path('/home/soundconsole/sound-machine/log/soundtrigger.log')
PLAY_RE  = re.compile(r'^PLAY:\s+button=(\d+)')


def journal_monitor():
    """Poll the soundtrigger log file directly for new PLAY lines.

    Using direct file reads instead of a tail subprocess avoids the
    pipe-buffering issue where tail holds output in a 4 KB block buffer
    before flushing, causing button presses to be invisible to the kiosk.
    Starting from the current end-of-file means only new presses (after
    server start) are captured — correct behaviour on restart.
    """
    # Start from the current end of the file so stale history is ignored
    log_pos = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0

    while True:
        try:
            if LOG_PATH.exists():
                current_size = LOG_PATH.stat().st_size
                # Handle log rotation / truncation
                if current_size < log_pos:
                    log_pos = 0
                if current_size > log_pos:
                    with open(LOG_PATH, 'r', errors='replace') as f:
                        f.seek(log_pos)
                        for line in f:
                            m = PLAY_RE.match(line.strip())
                            if m:
                                btn = int(m.group(1))
                                with _lock:
                                    _state['last_button'] = btn
                        log_pos = f.tell()
        except Exception:
            pass
        time.sleep(0.2)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    t = threading.Thread(target=journal_monitor, daemon=True)
    t.start()
    print("Kiosk server starting on http://0.0.0.0:8081 …", flush=True)
    app.run(host='0.0.0.0', port=8081, debug=False, threaded=True)
