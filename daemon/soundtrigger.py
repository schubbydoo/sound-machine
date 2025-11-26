#!/usr/bin/env python3
"""
Sound Machine trigger daemon - Database Driven
- Reads Pico USB CDC (serial) lines in the format: P,<id>\n
- Queries SQLite DB for active profile and button mapping
- Plays mapped WAV via aplay with immediate interruption
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
import threading
import sqlite3
from pathlib import Path
from typing import Optional

try:
    import serial  # pyserial
except Exception as exc:  # pragma: no cover
    print(f"ERROR: pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)

# LED daemon communication via named pipe
LED_FIFO = Path("/tmp/sound_led_events")
PRESS_RE = re.compile(r"^P,(\d{1,2})\s*$")
DB_PATH = Path("/home/soundconsole/sound-machine/data/sound_machine.db")

# Default Audio for "Not Assigned" (Placeholder)
NO_SOUND_FILE = Path("/home/soundconsole/sound-machine/Sounds/system/not_assigned.wav")


def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"DB Connection Error: {e}", file=sys.stderr)
        return None


def get_system_config(key: str, default: str = None) -> str:
    conn = get_db_connection()
    if not conn:
        return default
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default
    except Exception:
        return default
    finally:
        conn.close()


def get_audio_path(btn_id: int) -> Optional[Path]:
    """
    Query DB for the audio file path assigned to the button 
    for the currently active channel/profile.
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        
        # 1. Get active channel
        cursor.execute("SELECT value FROM system_config WHERE key = 'active_channel'")
        row = cursor.fetchone()
        if not row:
            return None
        active_channel = int(row['value'])
        
        # 2. Get profile for channel
        cursor.execute("SELECT profile_id FROM channels WHERE channel_number = ?", (active_channel,))
        row = cursor.fetchone()
        if not row:
            # Channel not configured or no profile
            return None
        profile_id = row['profile_id']
        
        # 3. Get audio file for button in profile
        cursor.execute(
            """
            SELECT a.filepath 
            FROM button_mappings bm
            JOIN audio_files a ON bm.audio_file_id = a.id
            WHERE bm.profile_id = ? AND bm.button_id = ?
            """, 
            (profile_id, btn_id)
        )
        row = cursor.fetchone()
        
        if row and row['filepath']:
            return Path(row['filepath'])
        
        return None
        
    except Exception as e:
        print(f"DB Query Error: {e}", file=sys.stderr)
        return None
    finally:
        conn.close()


def open_serial(port: str, baudrate: int = 115200, timeout: float = 0.5) -> serial.Serial:
    """Open serial connection with simple, reliable settings"""
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
    return ser


def resolve_serial_port(preferred: str) -> Optional[str]:
    """Return a usable serial device path."""
    try:
        p = Path(preferred)
        if p.exists():
            return str(p)
    except Exception:
        pass

    # Prefer stable by-id paths when available
    by_id = Path("/dev/serial/by-id")
    if by_id.exists():
        candidates = sorted(by_id.glob("*"))
        # Prefer Pico-like names if present
        pico_first = sorted(
            [c for c in candidates if "Pico" in c.name or "RP2040" in c.name]
        )
        for c in pico_first + [c for c in candidates if c not in pico_first]:
            try:
                if c.exists():
                    return str(c)
            except Exception:
                continue

    # Fallback to first ACM device
    for dev in sorted(Path("/dev").glob("ttyACM*")):
        try:
            if dev.exists():
                return str(dev)
        except Exception:
            continue
    return None


def check_audio_device(device: str) -> bool:
    """Check if audio device is available"""
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=1.0
        )
        return result.returncode == 0
    except Exception:
        return False


def send_button_event_to_led_daemon(btn_id: int) -> None:
    """Send button press event to LED daemon via named pipe"""
    def write_to_led_fifo():
        try:
            if LED_FIFO.exists():
                try:
                    fd = os.open(str(LED_FIFO), os.O_WRONLY | os.O_NONBLOCK)
                    os.write(fd, f"{btn_id}\n".encode())
                    os.close(fd)
                except (BlockingIOError, OSError):
                    try:
                        with open(str(LED_FIFO), 'w') as fifo:
                            fifo.write(f"{btn_id}\n")
                            fifo.flush()
                    except (OSError, BrokenPipeError):
                        pass
        except Exception:
            pass
    
    t = threading.Thread(target=write_to_led_fifo, daemon=True)
    t.start()


def send_led_stop_signal() -> None:
    """Send stop signal (button ID 0) to LED daemon to stop flashing"""
    send_button_event_to_led_daemon(0)


def play_wav_interruptible(wav_path: Path, device: str, current_process: Optional[subprocess.Popen], btn_id: int) -> Optional[subprocess.Popen]:
    """Play a WAV file, interrupting any current playback."""
    if not wav_path.exists():
        print(f"WAV not found: {wav_path}", file=sys.stderr)
        return None
    
    # Check if audio device is available
    if not check_audio_device(device):
        print(f"ERROR: Audio device '{device}' not available", file=sys.stderr)
        return None
    
    # Force kill any stuck process
    if current_process:
        try:
            if current_process.poll() is None:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    current_process.kill()
                    current_process.wait(timeout=0.5)
        except Exception as e:
            print(f"WARN: Error killing process: {e}", file=sys.stderr)
    
    cmd = [
        "aplay",
        "-q",
        "-D", device,
        str(wav_path),
    ]
    
    try:
        print(f"PLAY: button={btn_id} file={wav_path} device={device}")
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.1)
        if process.poll() is not None:
            print(f"ERROR: aplay exited immediately", file=sys.stderr)
            return None
        return process
    except Exception as e:
        print(f"ERROR: Failed to start playback: {e}", file=sys.stderr)
        return None


def main() -> int:
    # Initial configuration
    configured_port = get_system_config("serial", "/dev/ttyACM0")
    aplay_device = get_system_config("aplayDevice", "default")
    
    current_process: Optional[subprocess.Popen] = None
    current_button: Optional[int] = None
    
    last_press_ts: Dict[int, float] = {}
    debounce_ms = 200.0
    
    def cleanup_debounce_dict():
        nonlocal last_press_ts
        current_time = time.time() * 1000.0
        keys_to_remove = [k for k, v in last_press_ts.items() if (current_time - v) > 60000.0]
        for k in keys_to_remove:
            last_press_ts.pop(k, None)

    stop = False

    def handle_sig(signum, frame):
        nonlocal stop, current_process
        stop = True
        if current_process and current_process.poll() is None:
            current_process.terminate()
            try:
                current_process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                current_process.kill()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    
    # Audio device health monitor
    def monitor_audio_device():
        last_check = time.time()
        while not stop:
            try:
                if time.time() - last_check >= 2.0:
                    if not check_audio_device(aplay_device):
                        print(f"WARN: Audio device '{aplay_device}' disappeared", file=sys.stderr)
                    last_check = time.time()
                time.sleep(0.5)
            except Exception:
                time.sleep(2.0)
    
    audio_monitor_thread = threading.Thread(target=monitor_audio_device, daemon=True)
    audio_monitor_thread.start()

    # Playback monitor
    def monitor_audio_playback():
        nonlocal current_process, current_button
        last_signaled_process_id = None
        while not stop:
            try:
                if current_process and current_process.poll() is not None:
                    current_process_id = id(current_process)
                    if last_signaled_process_id != current_process_id:
                        print(f"PLAY_END: Audio finished for button {current_button}")
                        send_led_stop_signal()
                        last_signaled_process_id = current_process_id
                else:
                    if current_process:
                        last_signaled_process_id = None
                time.sleep(0.1)
            except Exception:
                time.sleep(0.5)
    
    playback_monitor_thread = threading.Thread(target=monitor_audio_playback, daemon=True)
    playback_monitor_thread.start()

    current_port: Optional[str] = None
    backoff_s = 0.5
    print(f"Sound trigger daemon starting (DB mode).", flush=True)
    
    try:
        subprocess.run(['amixer', '-c', '0', 'set', 'Speaker', '100%'], capture_output=True, timeout=2)
    except Exception:
        pass
    
    ser = None
    while not stop:
        try:
            if not ser or not current_port:
                current_port = resolve_serial_port(configured_port)
                if not current_port:
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 1.5, 5.0)
                    continue
                print(f"Opening serial: {current_port}", flush=True)
                ser = open_serial(current_port)
                print("Serial open; trigger loop ready.", flush=True)
                backoff_s = 0.5
            
            try:
                while not stop:
                    try:
                        line = ser.readline().decode("ascii", errors="ignore")
                    except (serial.SerialException, OSError):
                        print(f"[SERIAL ERROR]", flush=True)
                        ser = None
                        current_port = None
                        break
                    
                    if not line:
                        continue
                    
                    m = PRESS_RE.match(line)
                    if not m:
                        continue

                    btn_id = int(m.group(1))
                    now_ms = time.time() * 1000.0
                    last_ms = last_press_ts.get(btn_id, 0.0)
                    if (now_ms - last_ms) < debounce_ms:
                        continue
                    last_press_ts[btn_id] = now_ms
                    
                    if len(last_press_ts) > 20:
                        cleanup_debounce_dict()

                    # QUERY DB FOR AUDIO
                    wav_path = get_audio_path(btn_id)
                    
                    if not wav_path:
                        print(f"No audio assigned for button {btn_id} on active profile", flush=True)
                        if NO_SOUND_FILE.exists():
                             wav_path = NO_SOUND_FILE
                        else:
                             continue

                    try:
                        # Refresh device config periodically? For now assume static
                        current_process = play_wav_interruptible(wav_path, aplay_device, current_process, btn_id)
                        current_button = btn_id
                        send_button_event_to_led_daemon(btn_id)
                    except Exception as e:
                        print(f"Error playing button {btn_id}: {e}", file=sys.stderr, flush=True)
            
            except Exception as e:
                print(f"Inner loop error: {e}", flush=True)
                ser = None
                current_port = None
                time.sleep(1)
        
        except Exception as e:
            print(f"Outer loop error: {e}", flush=True)
            if ser:
                try: ser.close()
                except: pass
                ser = None
            current_port = None
            time.sleep(backoff_s)

    print("Exiting.")
    if current_process and current_process.poll() is None:
        current_process.terminate()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
