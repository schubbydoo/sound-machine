#!/usr/bin/env python3
"""
Memory Spark Station - Kiosk Server
Sidecar service: serves touchscreen UI on port 8081.
Monitors soundtrigger journal for last-pressed button.
Zero modifications to existing sound-machine services.
"""
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from flask import Flask, render_template, jsonify
except ImportError:
    print("Flask not found. Use the sound-machine venv.", file=sys.stderr)
    sys.exit(1)

DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')

app = Flask(__name__)

# Shared state protected by lock
_state = {'last_button': None}
_lock = threading.Lock()


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
        conn.execute(sql, args)
        conn.commit()
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


def get_channels():
    """Return dict channel_number -> {id, name, instruction}."""
    rows = _query("""
        SELECT c.channel_number, c.profile_id, p.name, p.instructions
        FROM channels c
        LEFT JOIN profiles p ON c.profile_id = p.id
        ORDER BY c.channel_number
    """)
    result = {}
    for r in rows:
        result[r['channel_number']] = {
            'id':          r['profile_id'],
            'name':        r['name'] or 'Unassigned',
            'instruction': r['instructions'] or '',
        }
    return result


def get_button_data(profile_id, button_id):
    """Return hint and answer for a button in a profile."""
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
    return {
        'hint':   r['hint'] or None,
        'answer': r['description'] or None,
    }


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('kiosk.html')


@app.route('/api/state')
def api_state():
    active_channel = int(get_config('active_channel', '1'))
    channels = get_channels()

    with _lock:
        last_button = _state['last_button']

    channel_info = channels.get(active_channel, {})
    profile_id   = channel_info.get('id')
    button_data  = get_button_data(profile_id, last_button)

    return jsonify({
        'active_channel': active_channel,
        'channels':       {str(k): v for k, v in channels.items()},
        'last_button':    last_button,
        'hint':           button_data['hint'],
        'answer':         button_data['answer'],
        'instruction':    channel_info.get('instruction', ''),
    })


@app.route('/api/channel/<int:n>', methods=['POST'])
def api_set_channel(n):
    if n not in (1, 2, 3, 4):
        return jsonify({'ok': False, 'error': 'Invalid channel'}), 400
    set_config('active_channel', n)
    with _lock:
        _state['last_button'] = None   # clear on track switch
    return jsonify({'ok': True})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Kill any currently playing audio (aplay process)."""
    subprocess.run(['pkill', '-x', 'aplay'], capture_output=True)
    return jsonify({'ok': True})


# ── Log file monitor ────────────────────────────────────────────────────────

LOG_PATH = Path('/home/soundconsole/sound-machine/log/soundtrigger.log')
PLAY_RE  = re.compile(r'^PLAY:\s+button=(\d+)')


def journal_monitor():
    """Background thread: tail soundtrigger log file for button presses."""
    while True:
        try:
            proc = subprocess.Popen(
                ['tail', '-F', str(LOG_PATH)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for line in proc.stdout:
                m = PLAY_RE.match(line.strip())
                if m:
                    btn = int(m.group(1))
                    with _lock:
                        _state['last_button'] = btn
            proc.wait()
        except Exception:
            pass
        time.sleep(2)


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    t = threading.Thread(target=journal_monitor, daemon=True)
    t.start()
    print("Kiosk server starting on http://0.0.0.0:8081 …", flush=True)
    app.run(host='0.0.0.0', port=8081, debug=False, threaded=True)
