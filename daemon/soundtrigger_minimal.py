#!/usr/bin/env python3
"""
Minimal Sound Machine trigger daemon
- Read button presses from Pico serial
- Play WAV files
- Signal LED daemon when buttons pressed
"""
import json
import os
import re
import sys
import time
import subprocess
import threading
from pathlib import Path

# Configuration
CONFIG_PATH = Path("/home/soundconsole/sound-machine/config/mappings.json")
SERIAL_PORT = "/dev/ttyACM0"
BUTTON_REGEX = re.compile(r"^P,(\d{1,2})\s*$")
LED_FIFO = Path("/tmp/sound_led_events")

def send_to_led_daemon(btn_id):
    """Send button event to LED daemon in background thread"""
    def write_led():
        try:
            if LED_FIFO.exists():
                with open(str(LED_FIFO), 'w') as f:
                    f.write(f"{btn_id}\n")
                    f.flush()
        except:
            pass
    
    # Don't block the main loop waiting for LED daemon
    t = threading.Thread(target=write_led, daemon=True)
    t.start()

def send_led_stop_signal():
    """Send stop signal (button ID 0) to LED daemon"""
    send_to_led_daemon(0)

def load_config():
    """Load button mappings"""
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    profile = cfg['profiles'][cfg['activeProfile']]
    base_dir = Path(profile['baseDir'])
    aplay_device = cfg.get('device', {}).get('aplayDevice', 'default')
    
    # Build button -> file mapping
    mapping = {}
    for btn_id, filename in profile['buttons'].items():
        if filename:
            mapping[int(btn_id)] = base_dir / filename
    
    return mapping, aplay_device

def play_sound(file_path, device, current_process):
    """Play a WAV file, interrupting any current playback"""
    if not file_path.exists():
        return None
    
    # Kill previous playback if it's still running
    if current_process and current_process.poll() is None:
        try:
            current_process.terminate()
            current_process.wait(timeout=0.5)
        except:
            try:
                current_process.kill()
            except:
                pass
    
    try:
        # Start new playback
        process = subprocess.Popen(
            ['aplay', '-q', '-D', device, str(file_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return process
    except Exception as e:
        print(f"Error playing {file_path}: {e}", file=sys.stderr)
        return None

def main():
    print("Sound Machine Minimal Daemon Starting", flush=True)
    
    try:
        button_mapping, aplay_device = load_config()
        print(f"Loaded {len(button_mapping)} button mappings", flush=True)
    except Exception as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 1
    
    # Playback monitor thread - watches audio process and sends LED stop when it finishes
    def monitor_playback():
        nonlocal current_process
        last_process_id = None
        while True:
            try:
                if current_process and current_process.poll() is not None:
                    # Audio finished - send stop signal to LED daemon
                    process_id = id(current_process)
                    if last_process_id != process_id:
                        send_led_stop_signal()
                        last_process_id = process_id
                else:
                    # Audio still playing - reset tracker for next audio
                    if current_process:
                        last_process_id = None
                time.sleep(0.1)
            except:
                time.sleep(0.1)
    
    monitor_thread = threading.Thread(target=monitor_playback, daemon=True)
    monitor_thread.start()
    
    # Main loop
    import serial
    last_press = {}
    current_process = None
    
    while True:
        try:
            with serial.Serial(SERIAL_PORT, 115200, timeout=2) as ser:
                print("Serial connected", flush=True)
                
                while True:
                    try:
                        line = ser.readline().decode("ascii", errors="ignore").strip()
                    except:
                        break
                    
                    if not line:
                        continue
                    
                    m = BUTTON_REGEX.match(line)
                    if not m:
                        continue
                    
                    btn_id = int(m.group(1))
                    
                    # Simple debounce (200ms)
                    now = time.time()
                    if now - last_press.get(btn_id, 0) < 0.2:
                        continue
                    last_press[btn_id] = now
                    
                    # Get and play file
                    file_path = button_mapping.get(btn_id)
                    if file_path:
                        print(f"Button {btn_id}: {file_path.name}", flush=True)
                        send_to_led_daemon(btn_id)  # Signal LED daemon
                        current_process = play_sound(file_path, aplay_device, current_process)
        
        except serial.SerialException:
            print("Serial disconnected, reconnecting...", flush=True)
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            time.sleep(1)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

