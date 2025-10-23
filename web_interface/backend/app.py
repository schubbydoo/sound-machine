#!/usr/bin/env python3
import json
import os
import subprocess
import shutil
import tempfile
import contextlib
import wave
from pathlib import Path
import threading
import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import subprocess
import shlex

APP_ROOT = Path('/home/soundconsole/sound-machine')
CONFIG_PATH = APP_ROOT / 'config' / 'mappings.json'
WIFI_CONFIG_PATH = APP_ROOT / 'config' / 'wifi.json'
BT_CONFIG_PATH = APP_ROOT / 'config' / 'bt.json'

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit for uploads


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_effects_mapping(cfg):
    profile = cfg['profiles'][cfg['activeProfile']]
    base_dir = Path(profile['baseDir'])
    buttons = profile['buttons']
    # Return list of (id, absolute_path, name)
    out = []
    for i in range(1, 17):
        key = str(i)
        rel = buttons.get(key, '')
        path = (base_dir / rel).resolve() if rel else None
        out.append({
            'id': i,
            'name': rel or '',
            'exists': bool(rel) and path.exists(),
            'path': str(path) if rel else ''
        })
    return out, cfg.get('device', {}).get('aplayDevice', 'default'), base_dir


def list_wavs(base_dir: Path):
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)
    wavs = [f for f in os.listdir(base_dir) if f.lower().endswith('.wav')]
    wavs.sort(key=str.lower)
    return wavs


# ---------------- WAV validation/conversion ----------------
TARGET_RATE = 48000  # Hz
TARGET_WIDTH_BYTES = 2  # 16-bit PCM


def _have_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def probe_wav(path: Path) -> dict:
    """Return basic WAV info or {} on failure."""
    try:
        with contextlib.closing(wave.open(str(path), 'rb')) as w:
            info = {
                'channels': w.getnchannels(),
                'sampwidth': w.getsampwidth(),
                'framerate': w.getframerate(),
                'nframes': w.getnframes(),
            }
            return info
    except Exception:
        return {}


def needs_conversion(path: Path) -> bool:
    info = probe_wav(path)
    if not info:
        return True
    if info['sampwidth'] != TARGET_WIDTH_BYTES:
        return True
    if info['framerate'] != TARGET_RATE:
        return True
    # accept mono or stereo
    if info['channels'] not in (1, 2):
        return True
    return False


def convert_wav(src: Path, dst: Path) -> None:
    """Convert wav to 48kHz 16-bit PCM using sox or ffmpeg."""
    if _have_cmd('sox'):
        cmd = [
            'sox', str(src),
            '-r', str(TARGET_RATE),
            '-e', 'signed-integer',
            '-b', '16',
            str(dst),
        ]
    elif _have_cmd('ffmpeg'):
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(src),
            '-ar', str(TARGET_RATE),
            '-acodec', 'pcm_s16le',
            str(dst),
        ]
    else:
        raise RuntimeError('Neither sox nor ffmpeg found for WAV conversion')
    subprocess.check_call(cmd)


# ---------------- Wi-Fi helpers ----------------
def wifi_load_config():
    if WIFI_CONFIG_PATH.exists():
        with open(WIFI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    else:
        cfg = {"autoConnect": False, "known": {}}
    # Normalize known entries to objects: {password, auto, priority}
    known = cfg.get("known", {})
    normalized = {}
    if isinstance(known, dict):
        for ssid, val in known.items():
            if isinstance(val, dict):
                normalized[ssid] = {
                    "password": val.get("password", ""),
                    "auto": bool(val.get("auto", False)),
                    "priority": int(val.get("priority", 0)),
                }
            else:
                # legacy string password format
                normalized[ssid] = {"password": str(val or ""), "auto": False, "priority": 0}
    cfg["known"] = normalized
    return cfg


def wifi_save_config(cfg):
    WIFI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WIFI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


def nm(cmd: str):
    try:
        return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output


def wifi_scan():
    # Ensure a fresh scan and use explicit 'list'
    _ = nm('nmcli dev wifi rescan')
    out = nm('nmcli -t -f SSID,SECURITY,SIGNAL dev wifi list')
    if not out.strip():
        # Fallback without 'list' (older nmcli variants)
        out = nm('nmcli -t -f SSID,SECURITY,SIGNAL dev wifi')
    nets = []
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split(':')
        if len(parts) < 3:
            continue
        ssid, sec, sig = parts[0], parts[1], parts[2]
        if ssid == '':
            continue
        nets.append({"ssid": ssid, "security": sec, "signal": int(sig or 0)})
    # Deduplicate by SSID, keep highest signal
    best = {}
    for n in nets:
        if n["ssid"] not in best or n["signal"] > best[n["ssid"]]["signal"]:
            best[n["ssid"]] = n
    nets = sorted(best.values(), key=lambda x: -x["signal"])
    return nets


# ---------------- Bluetooth helpers ----------------
def bt_load_config():
    if BT_CONFIG_PATH.exists():
        with open(BT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    else:
        cfg = {"known": {}, "default": ""}
    # Normalize structure
    known = cfg.get('known', {}) or {}
    norm = {}
    for mac, meta in known.items():
        if isinstance(meta, dict):
            norm[mac] = {"name": meta.get("name", "")}
        else:
            norm[mac] = {"name": str(meta)}
    cfg['known'] = norm
    cfg.setdefault('default', "")
    return cfg


def bt_save_config(cfg):
    BT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BT_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


def bt_run(cmd: str):
    try:
        return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output


def bt_scan(seconds: int = 6):
    # Trigger scan and list devices
    _ = bt_run(f'bluetoothctl --timeout {seconds} scan on')
    out = bt_run('bluetoothctl devices')
    devices = []
    for line in out.splitlines():
        # Format: Device XX:XX:XX:XX:XX:XX Name...
        parts = line.split(' ', 2)
        if len(parts) >= 3 and parts[0] == 'Device':
            mac = parts[1].strip()
            name = parts[2].strip()
            devices.append({"mac": mac, "name": name})
    return devices


def bt_paired():
    # Some versions prefer 'devices Paired'
    out = bt_run('bluetoothctl devices Paired')
    paired = []
    for line in out.splitlines():
        parts = line.split(' ', 2)
        if len(parts) >= 3 and parts[0] == 'Device':
            paired.append({"mac": parts[1].strip(), "name": parts[2].strip()})
    return paired


def bt_is_connected(mac: str) -> bool:
    info = bt_run(f'bluetoothctl info {shlex.quote(mac)}')
    return 'Connected: yes' in info


def bt_connect(mac: str):
    # Robust, stepwise connect with timeouts; avoid color escape codes by TERM=dumb
    env = os.environ.copy()
    env["TERM"] = "dumb"
    def run(cmd: str, timeout_s: float = 6.0) -> str:
        try:
            cp = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                timeout=timeout_s,
            )
            return cp.stdout
        except subprocess.TimeoutExpired as e:
            return (e.output or "") + "\n[TIMEOUT] " + cmd

    mac_q = shlex.quote(mac)
    out: list[str] = []
    # also append to a rotating file in log/
    log_dir = APP_ROOT / 'log'
    log_dir.mkdir(parents=True, exist_ok=True)
    bt_log = log_dir / 'bt_connect.log'
    out.append(run("rfkill unblock bluetooth || true", 3.0))
    out.append(run("bluetoothctl --timeout 4 power on || true", 5.0))
    out.append(run("bluetoothctl --timeout 4 agent NoInputNoOutput || true", 5.0))
    out.append(run("bluetoothctl --timeout 4 default-agent || true", 5.0))
    out.append(run("bluetoothctl --timeout 4 pairable on || true", 5.0))
    out.append(run(f"bluetoothctl --timeout 10 pair {mac_q} || true", 12.0))
    out.append(run(f"bluetoothctl --timeout 4 trust {mac_q} || true", 5.0))
    out.append(run(f"bluetoothctl --timeout 10 connect {mac_q} || true", 12.0))

    # Poll for connected state up to ~10s
    for _ in range(10):
        info = run(f"bluetoothctl info {mac_q} || true")
        out.append(info)
        if "Connected: yes" in info:
            break
        time.sleep(1)
    transcript = "\n".join(out)
    try:
        with bt_log.open('a', encoding='utf-8') as f:
            f.write("\n=== bt_connect ===\n")
            f.write(transcript)
            f.write("\n")
    except Exception:
        pass
    return transcript


def bt_set_default_sink(mac: str) -> str:
    """Set Pulse default sink to the bluez sink matching MAC, fallback no-op.

    Returns a short status string.
    """
    mac_u = mac.replace(":", "_")
    try:
        out = subprocess.check_output(["pactl", "list", "sinks", "short"], text=True)
    except Exception as exc:
        return f"pactl list sinks failed: {exc}"
    sink_name = ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and mac_u in parts[1] and "bluez_sink" in parts[1]:
            sink_name = parts[1]
            break
    if not sink_name:
        return "no bluez sink found"
    try:
        subprocess.check_call(["pactl", "set-default-sink", sink_name])
        return f"default sink set: {sink_name}"
    except Exception as exc:
        return f"set-default-sink failed: {exc}"


# ---------------- Async BT connect job ----------------
_bt_job_lock = threading.Lock()
_bt_job_running = False
_bt_job_last_mac = ""


def _bt_append_log(lines: str) -> None:
    try:
        log_dir = APP_ROOT / 'log'
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / 'bt_connect.log').open('a', encoding='utf-8') as f:
            f.write(lines)
    except Exception:
        pass


def _bt_run(cmd: str, timeout_s: float = 10.0) -> str:
    env = os.environ.copy()
    env['TERM'] = 'dumb'
    try:
        cp = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_s, env=env)
        return cp.stdout
    except subprocess.TimeoutExpired as e:
        out = e.output
        if isinstance(out, bytes):
            try:
                out = out.decode('utf-8', 'ignore')
            except Exception:
                out = ''
        out = out or ''
        return out + f"\n[TIMEOUT] {cmd}\n"


def _bt_connect_job(mac: str) -> None:
    global _bt_job_running
    try:
        ts = datetime.datetime.now().isoformat(timespec='seconds')
        _bt_append_log(f"\n=== bt_connect job start {ts} mac={mac} ===\n")
        mac_q = shlex.quote(mac)
        steps = [
            "rfkill unblock bluetooth || true",
            "bluetoothctl --timeout 4 power on || true",
            "bluetoothctl --timeout 4 agent NoInputNoOutput || true",
            "bluetoothctl --timeout 4 default-agent || true",
            "bluetoothctl --timeout 4 pairable on || true",
            f"bluetoothctl --timeout 12 pair {mac_q} || true",
            f"bluetoothctl --timeout 6 trust {mac_q} || true",
            f"bluetoothctl --timeout 12 connect {mac_q} || true",
        ]
        for s in steps:
            out = _bt_run(s)
            _bt_append_log(out)

        # Poll connected + set sink
        for _ in range(12):
            info = bt_run(f'bluetoothctl info {mac_q}')
            _bt_append_log(info)
            if 'Connected: yes' in info:
                _bt_append_log(bt_set_default_sink(mac) + "\n")
                break
            time.sleep(1)
    finally:
        with _bt_job_lock:
            _bt_job_running = False


def bt_forget(mac: str):
    return bt_run(f'bluetoothctl remove {shlex.quote(mac)}')


def wifi_connect(ssid: str, password: str):
    if password:
        cmd = f"nmcli dev wifi connect {shlex.quote(ssid)} password {shlex.quote(password)}"
    else:
        cmd = f"nmcli dev wifi connect {shlex.quote(ssid)}"
    out = nm(cmd)
    return out


def wifi_forget(ssid: str):
    out = nm('nmcli -t -f UUID,NAME con show')
    uuid = None
    for line in out.splitlines():
        if ':' in line:
            u, name = line.split(':', 1)
            if name == ssid:
                uuid = u
                break
    if uuid:
        return nm(f'nmcli con delete {uuid}')
    return 'No connection found'


def nm_find_connection_uuid(ssid: str):
    out = nm('nmcli -t -f UUID,NAME con show')
    for line in out.splitlines():
        if ':' in line:
            u, name = line.split(':', 1)
            if name == ssid:
                return u
    return None


def wifi_set_autopref(ssid: str, auto: bool, priority: int):
    uuid = nm_find_connection_uuid(ssid)
    if not uuid:
        return 'No connection found to modify'
    auto_val = 'yes' if auto else 'no'
    out1 = nm(f'nmcli con modify {uuid} connection.autoconnect {auto_val}')
    out2 = nm(f'nmcli con modify {uuid} connection.autoconnect-priority {priority}')
    return (out1 or '') + '\n' + (out2 or '')


@app.get('/')
def index():
    cfg = load_config()
    mapping, aplay_device, base_dir = get_effects_mapping(cfg)
    files = list_wavs(base_dir)
    return render_template('index.html', mapping=mapping, aplay_device=aplay_device, files=files)


@app.get('/wifi')
def wifi_page():
    nets = wifi_scan()
    wcfg = wifi_load_config()
    return render_template('wifi.html', nets=nets, wcfg=wcfg)


@app.get('/bt')
def bt_page():
    devices = bt_scan()
    paired = bt_paired()
    # annotate connection status
    for p in paired:
        p['connected'] = bt_is_connected(p['mac'])
    bcfg = bt_load_config()
    return render_template('bt.html', devices=devices, paired=paired, bcfg=bcfg)


@app.get('/bt/paired')
def bt_paired_api():
    items = bt_paired()
    for p in items:
        p['connected'] = bt_is_connected(p['mac'])
    return jsonify({'ok': True, 'paired': items})


@app.post('/wifi/connect')
def wifi_connect_route():
    ssid = request.form.get('ssid') or (request.is_json and request.json.get('ssid'))
    password = request.form.get('password') or (request.is_json and request.json.get('password')) or ''
    if not ssid:
        return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    out = wifi_connect(ssid, password)
    return jsonify({'ok': True, 'output': out})


@app.post('/wifi/remember')
def wifi_remember():
    ssid = request.form.get('ssid') or (request.is_json and request.json.get('ssid'))
    password = request.form.get('password') or (request.is_json and request.json.get('password')) or ''
    if not ssid:
        return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    cfg = wifi_load_config()
    cfg.setdefault('known', {})[ssid] = cfg['known'].get(ssid, {"password":"", "auto": False, "priority": 0})
    cfg['known'][ssid]['password'] = password
    wifi_save_config(cfg)
    return jsonify({'ok': True})


@app.post('/wifi/forget')
def wifi_forget_route():
    ssid = request.form.get('ssid') or (request.is_json and request.json.get('ssid'))
    if not ssid:
        return jsonify({'ok': False, 'error': 'Missing SSID'}), 400
    out = wifi_forget(ssid)
    cfg = wifi_load_config()
    if cfg.get('known', {}).pop(ssid, None) is not None:
        wifi_save_config(cfg)
    return jsonify({'ok': True, 'output': out})


@app.post('/wifi/auto')
def wifi_auto_toggle():
    payload = request.json if request.is_json else request.form
    ssid = payload.get('ssid') if payload else None
    enable = payload.get('enable') if payload else None
    priority = payload.get('priority') if payload else None
    if ssid:
        # Per-SSID control
        try:
            prio = int(priority if priority is not None else 0)
        except Exception:
            prio = 0
        en = str(enable).lower() in ('1','true','yes','on')
        cfg = wifi_load_config()
        cfg.setdefault('known', {})[ssid] = cfg['known'].get(ssid, {"password":"", "auto": False, "priority": 0})
        cfg['known'][ssid]['auto'] = en
        cfg['known'][ssid]['priority'] = prio
        wifi_save_config(cfg)
        nm_out = wifi_set_autopref(ssid, en, prio)
        return jsonify({'ok': True, 'ssid': ssid, 'auto': en, 'priority': prio, 'nm': nm_out})
    else:
        # Global toggle retained for completeness
        en = str(enable).lower() in ('1', 'true', 'yes', 'on') if enable is not None else False
        cfg = wifi_load_config()
        cfg['autoConnect'] = en
        wifi_save_config(cfg)
        return jsonify({'ok': True, 'autoConnect': en})


@app.post('/bt/connect')
def bt_connect_route():
    mac = (request.json or request.form).get('mac') if (request.is_json or request.form) else None
    if not mac:
        return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    out = bt_connect(mac)
    sink_status = bt_set_default_sink(mac)
    return jsonify({'ok': True, 'output': out, 'sink': sink_status})


@app.post('/bt/connect_start')
def bt_connect_start():
    mac = (request.json or request.form).get('mac') if (request.is_json or request.form) else None
    if not mac:
        return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    global _bt_job_running, _bt_job_last_mac
    with _bt_job_lock:
        if not _bt_job_running:
            _bt_job_running = True
            _bt_job_last_mac = mac
            t = threading.Thread(target=_bt_connect_job, args=(mac,), daemon=True)
            t.start()
    return jsonify({'ok': True, 'running': True, 'mac': mac})


@app.get('/bt/status')
def bt_status():
    # Return paired devices with connection flags, current default sink and recent transcript
    items = bt_paired()
    for p in items:
        p['connected'] = bt_is_connected(p['mac'])
    try:
        with (APP_ROOT / 'log' / 'bt_connect.log').open('r', encoding='utf-8') as f:
            data = f.read()
            transcript = data[-5000:] if len(data) > 5000 else data
    except Exception:
        transcript = ''
    # default sink
    try:
        info = subprocess.check_output(['pactl', 'info'], text=True)
        default_sink = next((ln.split(':',1)[1].strip() for ln in info.splitlines() if ln.startswith('Default Sink:')), '')
    except Exception:
        default_sink = ''
    return jsonify({'ok': True, 'paired': items, 'default_sink': default_sink, 'transcript': transcript})


@app.post('/bt/remember')
def bt_remember():
    data = request.json if request.is_json else request.form
    mac = data.get('mac')
    name = data.get('name', '')
    make_default = str(data.get('default', '')).lower() in ('1','true','yes','on')
    if not mac:
        return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    cfg = bt_load_config()
    cfg.setdefault('known', {})[mac] = {"name": name}
    if make_default:
        cfg['default'] = mac
    bt_save_config(cfg)
    return jsonify({'ok': True})


@app.post('/bt/forget')
def bt_forget_route():
    mac = (request.json or request.form).get('mac') if (request.is_json or request.form) else None
    if not mac:
        return jsonify({'ok': False, 'error': 'Missing MAC'}), 400
    out = bt_forget(mac)
    cfg = bt_load_config()
    if cfg.get('known', {}).pop(mac, None) is not None:
        if cfg.get('default') == mac:
            cfg['default'] = ''
        bt_save_config(cfg)
    return jsonify({'ok': True, 'output': out})


@app.post('/play/<int:button_id>')
def play(button_id: int):
    cfg = load_config()
    mapping, aplay_device, _ = get_effects_mapping(cfg)
    entry = next((e for e in mapping if e['id'] == button_id), None)
    if not entry or not entry['exists']:
        return jsonify({'ok': False, 'error': 'No file mapped'}), 400
    cmd = ['aplay', '-q', '-D', aplay_device, entry['path']]
    try:
        rc = subprocess.call(cmd)
    except FileNotFoundError:
        return jsonify({'ok': False, 'error': 'aplay not found'}), 500
    return jsonify({'ok': rc == 0, 'rc': rc})


@app.post('/upload')
def upload():
    cfg = load_config()
    _, __, base_dir = get_effects_mapping(cfg)
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'Empty filename'}), 400
    name = secure_filename(f.filename)
    if not name.lower().endswith('.wav'):
        return jsonify({'ok': False, 'error': 'Only .wav supported'}), 400
    base_dir.mkdir(parents=True, exist_ok=True)
    dest = base_dir / name
    # Save to temp then validate/convert if needed
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
        tmp_path = Path(tmp.name)
        f.save(str(tmp_path))
    try:
        if needs_conversion(tmp_path):
            try:
                convert_wav(tmp_path, dest)
            except Exception as e:
                # Fallback: if conversion failed but original is okay enough, keep original
                info = probe_wav(tmp_path)
                if info:
                    tmp_path.replace(dest)
                else:
                    return jsonify({'ok': False, 'error': f'Conversion failed: {e}'}), 500
        else:
            tmp_path.replace(dest)
    finally:
        with contextlib.suppress(Exception):
            if tmp_path.exists():
                tmp_path.unlink()
    return jsonify({'ok': True, 'name': name})


@app.post('/delete')
def delete_file():
    cfg = load_config()
    _, __, base_dir = get_effects_mapping(cfg)
    name = request.form.get('name') or (request.is_json and request.json.get('name'))
    if not name:
        return jsonify({'ok': False, 'error': 'Missing name'}), 400
    # Only allow deletion within base_dir
    target = (base_dir / name).resolve()
    if base_dir not in target.parents and target != base_dir:
        return jsonify({'ok': False, 'error': 'Invalid path'}), 400
    if target.exists():
        try:
            target.unlink()
        except Exception as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 500
    # Optionally clear mappings that referenced this name
    changed = False
    buttons = cfg['profiles'][cfg['activeProfile']]['buttons']
    for k, v in list(buttons.items()):
        if v == name:
            buttons[k] = ''
            changed = True
    if changed:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    return jsonify({'ok': True})


@app.post('/assign')
def assign():
    cfg = load_config()
    profile_name = cfg['activeProfile']
    buttons = cfg['profiles'][profile_name]['buttons']
    try:
        if request.is_json:
            payload = request.json
        else:
            payload = request.form
        btn_id = int(payload.get('button'))
        name = payload.get('name', '')
    except Exception:
        return jsonify({'ok': False, 'error': 'Invalid params'}), 400
    buttons[str(btn_id)] = name
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    return jsonify({'ok': True})


@app.post('/assign_bulk')
def assign_bulk():
    cfg = load_config()
    profile_name = cfg['activeProfile']
    buttons = cfg['profiles'][profile_name]['buttons']
    if not request.is_json:
        return jsonify({'ok': False, 'error': 'Expected JSON'}), 400
    payload = request.json or {}
    if not isinstance(payload, dict):
        return jsonify({'ok': False, 'error': 'Invalid JSON'}), 400
    for k, v in payload.items():
        try:
            k_int = int(k)
        except Exception:
            continue
        buttons[str(k_int)] = v or ''
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
