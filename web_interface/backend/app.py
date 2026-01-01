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
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response

try:
    from werkzeug.utils import secure_filename
except ImportError:
    from werkzeug.utils import secure_filename

import backend.network_utils as nu

APP_ROOT = Path('/home/soundconsole/sound-machine')
DB_PATH = APP_ROOT / 'data' / 'sound_machine.db'
SOUNDS_ROOT = APP_ROOT / 'Sounds'

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit

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
            SELECT bm.button_id, af.filename, af.description, af.category, af.id as audio_id
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

    conn.close()
    
    return render_template('index.html', 
                           profiles=profiles, 
                           active_profile_id=int(active_profile_id) if active_profile_id else None,
                           mappings=mappings,
                           all_files=all_files,
                           channels=channels)

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
    return profile, rows

@app.route('/print_key/<int:profile_id>')
def print_key(profile_id):
    conn = get_db()
    p, r = get_profile_full_data(conn, profile_id)
    conn.close()
    return render_template('print_key.html', items=[{'profile': p, 'rows': r}])

@app.route('/print_key/assigned')
def print_key_assigned():
    conn = get_db()
    items = []
    # Get assigned profiles ordered by channel
    assigned = conn.execute("SELECT profile_id FROM channels WHERE channel_number BETWEEN 1 AND 4 ORDER BY channel_number").fetchall()
    for row in assigned:
        if row['profile_id']:
            p, r = get_profile_full_data(conn, row['profile_id'])
            items.append({'profile': p, 'rows': r})
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
    p, r = get_profile_full_data(conn, profile_id)
    conn.close()
    return render_template('print_worksheet.html', items=[{'profile': p, 'rows': r}])

@app.route('/print_worksheet/assigned')
def print_worksheet_assigned():
    conn = get_db()
    items = []
    assigned = conn.execute("SELECT profile_id FROM channels WHERE channel_number BETWEEN 1 AND 4 ORDER BY channel_number").fetchall()
    for row in assigned:
        if row['profile_id']:
            p, r = get_profile_full_data(conn, row['profile_id'])
            items.append({'profile': p, 'rows': r})
    conn.close()
    return render_template('print_worksheet.html', items=items)

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

@app.post('/play/<int:button_id>')
def play(button_id: int):
    # This route is for testing via UI
    # We should query DB for the active profile (hardware active channel if not specified?)
    # Or should the UI play the sound associated with the *displayed* profile?
    # Usually UI play testing should play what's on the screen.
    # But current app logic had `get_effects_mapping` using `activeProfile` from config.
    
    # We'll use the profile passed in query param or active channel?
    # UI should probably pass the file path or ID directly if testing a specific assignment.
    # But let's stick to button ID for now. 
    # Let's assume testing the *Hardware Active* profile if no profile_id is implicit?
    # Or better: UI usually sends button ID.
    
    # Let's fetch the audio for this button on the ACTIVE CHANNEL (Hardware) to simulate real press
    # OR fetch for the requested profile if we want to preview edits.
    # Existing app used `activeProfile`.
    
    # Let's see if we can get profile_id from request?
    # If not, use hardware active.
    
    conn = get_db()
    
    # Try to find what file is mapped
    # If we want to support previewing the profile being edited:
    profile_id = request.args.get('profile_id')
    
    if not profile_id:
        # Fallback to hardware active
        chn = get_system_config('active_channel', '1')
        row = conn.execute("SELECT profile_id FROM channels WHERE channel_number = ?", (chn,)).fetchone()
        profile_id = row['profile_id'] if row else None
        
    path = None
    if profile_id:
        row = conn.execute("""
            SELECT af.filepath 
            FROM button_mappings bm
            JOIN audio_files af ON bm.audio_file_id = af.id
            WHERE bm.profile_id = ? AND bm.button_id = ?
        """, (profile_id, button_id)).fetchone()
        if row: path = row['filepath']
        
    conn.close()
    
    if not path or not os.path.exists(path):
        return jsonify({'ok': False, 'error': 'No file mapped'}), 400
        
    aplay_device = get_system_config('aplayDevice', 'default')
    cmd = ['aplay', '-q', '-D', aplay_device, path]
    try:
        subprocess.Popen(cmd) # Fire and forget for UI test
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
