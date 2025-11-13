#!/usr/bin/env python3
"""
Minimal Sound Machine trigger daemon
- Read button presses from Pico serial
- Play WAV files
- No configuration reload, no LED signals, no threads
"""
import json
import os
import re
import sys
import time
import subprocess
from pathlib import Path

# Configuration
CONFIG_PATH = Path("/home/soundconsole/sound-machine/config/mappings.json")
SERIAL_PORT = "/dev/ttyACM0"
BUTTON_REGEX = re.compile(r"^P,(\d{1,2})\s*$")

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

def play_sound(file_path, device):
    """Play a WAV file"""
    if not file_path.exists():
        return False
    try:
        subprocess.run(
            ['aplay', '-q', '-D', device, str(file_path)],
            timeout=60,
            check=False
        )
        return True
    except Exception as e:
        print(f"Error playing {file_path}: {e}", file=sys.stderr)
        return False

def main():
    print("Sound Machine Minimal Daemon Starting", flush=True)
    
    try:
        button_mapping, aplay_device = load_config()
        print(f"Loaded {len(button_mapping)} button mappings", flush=True)
    except Exception as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 1
    
    # Main loop
    import serial
    last_press = {}
    
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
                        play_sound(file_path, aplay_device)
        
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

