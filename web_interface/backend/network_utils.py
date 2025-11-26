import json
import os
import shutil
import subprocess
import shlex
import time
import threading
import datetime
from pathlib import Path

APP_ROOT = Path('/home/soundconsole/sound-machine')
WIFI_CONFIG_PATH = APP_ROOT / 'config' / 'wifi.json'
BT_CONFIG_PATH = APP_ROOT / 'config' / 'bt.json'

def nm(cmd: str):
    try:
        return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output

def wifi_load_config():
    if WIFI_CONFIG_PATH.exists():
        try:
            with open(WIFI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except:
            cfg = {}
    else:
        cfg = {"autoConnect": False, "known": {}}
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
                normalized[ssid] = {"password": str(val or ""), "auto": False, "priority": 0}
    cfg["known"] = normalized
    return cfg

def wifi_save_config(cfg):
    WIFI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WIFI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

def wifi_scan():
    _ = nm('nmcli dev wifi rescan')
    out = nm('nmcli -t -f SSID,SECURITY,SIGNAL dev wifi list')
    if not out.strip():
        out = nm('nmcli -t -f SSID,SECURITY,SIGNAL dev wifi')
    nets = []
    for line in out.splitlines():
        if not line: continue
        parts = line.split(':')
        if len(parts) < 3: continue
        ssid, sec, sig = parts[0], parts[1], parts[2]
        if ssid == '': continue
        nets.append({"ssid": ssid, "security": sec, "signal": int(sig or 0)})
    best = {}
    for n in nets:
        if n["ssid"] not in best or n["signal"] > best[n["ssid"]]["signal"]:
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda x: -x["signal"])

def wifi_connect(ssid, password):
    if password:
        cmd = f"nmcli dev wifi connect {shlex.quote(ssid)} password {shlex.quote(password)}"
    else:
        cmd = f"nmcli dev wifi connect {shlex.quote(ssid)}"
    return nm(cmd)

def wifi_forget(ssid):
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

def wifi_set_autopref(ssid, auto, priority):
    out = nm('nmcli -t -f UUID,NAME con show')
    uuid = None
    for line in out.splitlines():
        if ':' in line:
            u, name = line.split(':', 1)
            if name == ssid:
                uuid = u
                break
    if not uuid:
        return 'No connection found to modify'
    auto_val = 'yes' if auto else 'no'
    out1 = nm(f'nmcli con modify {uuid} connection.autoconnect {auto_val}')
    out2 = nm(f'nmcli con modify {uuid} connection.autoconnect-priority {priority}')
    return (out1 or '') + '\n' + (out2 or '')

# BT Helpers
def bt_load_config():
    if BT_CONFIG_PATH.exists():
        try:
            with open(BT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except:
             cfg = {}
    else:
        cfg = {"known": {}, "default": ""}
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

def bt_run(cmd):
    try:
        return subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output

def bt_scan(seconds=6):
    _ = bt_run(f'bluetoothctl --timeout {seconds} scan on')
    out = bt_run('bluetoothctl devices')
    devices = []
    for line in out.splitlines():
        parts = line.split(' ', 2)
        if len(parts) >= 3 and parts[0] == 'Device':
            devices.append({"mac": parts[1].strip(), "name": parts[2].strip()})
    return devices

def bt_paired():
    out = bt_run('bluetoothctl devices Paired')
    paired = []
    for line in out.splitlines():
        parts = line.split(' ', 2)
        if len(parts) >= 3 and parts[0] == 'Device':
            paired.append({"mac": parts[1].strip(), "name": parts[2].strip()})
    return paired

def bt_is_connected(mac):
    info = bt_run(f'bluetoothctl info {shlex.quote(mac)}')
    return 'Connected: yes' in info

def bt_forget(mac):
    return bt_run(f'bluetoothctl remove {shlex.quote(mac)}')

def bt_set_default_sink(mac):
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

_bt_job_lock = threading.Lock()
_bt_job_running = False

def _bt_append_log(lines):
    try:
        log_dir = APP_ROOT / 'log'
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / 'bt_connect.log').open('a', encoding='utf-8') as f:
            f.write(lines)
    except: pass

def _bt_run_cmd(cmd, timeout_s=10.0):
    env = os.environ.copy()
    env['TERM'] = 'dumb'
    try:
        cp = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_s, env=env)
        return cp.stdout
    except subprocess.TimeoutExpired as e:
        out = e.output
        if isinstance(out, bytes): out = out.decode('utf-8', 'ignore')
        return (out or '') + f"\n[TIMEOUT] {cmd}\n"

def bt_connect_job(mac):
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
            out = _bt_run_cmd(s)
            _bt_append_log(out)

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

def start_bt_connect_thread(mac):
    global _bt_job_running
    with _bt_job_lock:
        if not _bt_job_running:
            _bt_job_running = True
            t = threading.Thread(target=bt_connect_job, args=(mac,), daemon=True)
            t.start()
            return True
    return False

def bt_connect_sync(mac):
    # Synchronous connect for simple use cases
    env = os.environ.copy()
    env["TERM"] = "dumb"
    def run(cmd, timeout_s=6.0):
        try:
            cp = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, timeout=timeout_s)
            return cp.stdout
        except subprocess.TimeoutExpired as e:
            return (e.output or "") + "\n[TIMEOUT]"
            
    mac_q = shlex.quote(mac)
    out = []
    out.append(run("rfkill unblock bluetooth || true", 3.0))
    out.append(run("bluetoothctl --timeout 4 power on || true", 5.0))
    out.append(run(f"bluetoothctl --timeout 10 connect {mac_q} || true", 12.0))
    return "\n".join(out)

