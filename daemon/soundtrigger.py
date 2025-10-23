#!/usr/bin/env python3
"""
Sound Machine trigger daemon - Optimized for responsiveness
- Reads Pico USB CDC (serial) lines in the format: P,<id>\n
- Plays mapped WAV via aplay with immediate interruption
- Sends LED override: L,<id>,1 during playback, then L,<id>,0
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import serial  # pyserial
except Exception as exc:  # pragma: no cover
    print(f"ERROR: pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)

PRESS_RE = re.compile(r"^P,(\d{1,2})\s*$")

DEFAULT_CONFIG_PATH = Path(
    os.environ.get("SOUND_MACHINE_CONFIG", "/home/soundconsole/sound-machine/config/mappings.json")
)


def load_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_active_profile(config: Dict[str, Any]) -> Dict[str, Any]:
    profile_name = config.get("activeProfile")
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise KeyError(f"Active profile '{profile_name}' not found in config")
    return profiles[profile_name]


def build_button_map(profile_cfg: Dict[str, Any]) -> Dict[int, Path]:
    base_dir = Path(profile_cfg.get("baseDir", ".")).expanduser()
    buttons = profile_cfg.get("buttons", {})
    mapping: Dict[int, Path] = {}
    for key, rel in buttons.items():
        try:
            btn_id = int(key)
        except Exception:
            continue
        if not rel:
            continue
        mapping[btn_id] = (base_dir / rel).resolve()
    return mapping


def open_serial(port: str, baudrate: int = 115200, timeout: float = 0.1) -> serial.Serial:
    """Open serial connection with improved stability settings"""
    ser = serial.Serial(
        port=port, 
        baudrate=baudrate, 
        timeout=timeout,
        write_timeout=1.0,
        inter_byte_timeout=0.1,
        rtscts=False,  # Disable hardware flow control
        dsrdtr=False,  # Disable hardware flow control
        xonxoff=False  # Disable software flow control
    )
    # Clear any existing data
    ser.reset_input_buffer()
    ser.reset_output_buffer()
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


# LED functions removed - no LEDs on this switch board


def play_wav_interruptible(wav_path: Path, device: str, current_process: Optional[subprocess.Popen], btn_id: int) -> Optional[subprocess.Popen]:
    """Play a WAV file, interrupting any current playback."""
    if not wav_path.exists():
        print(f"WAV not found: {wav_path}", file=sys.stderr)
        return current_process
    
    # Complete audio system reset to prevent race conditions
    try:
        # Kill ALL audio processes aggressively
        subprocess.run(['pkill', '-9', '-f', 'aplay'], capture_output=True, timeout=1)
        subprocess.run(['pkill', '-9', '-f', 'pulseaudio'], capture_output=True, timeout=1)
        subprocess.run(['pkill', '-9', '-f', 'sox'], capture_output=True, timeout=1)
        # Reset ALSA to clear any stuck buffers
        subprocess.run(['alsactl', 'restore'], capture_output=True, timeout=2)
        # Wait for system to stabilize
        time.sleep(0.2)
    except Exception as e:
        print(f"Audio cleanup warning: {e}", file=sys.stderr)
    
    # Stop current playback with timeout
    if current_process and current_process.poll() is None:
        print(f"STOP: interrupting current playback")
        try:
            current_process.terminate()
            current_process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            try:
                current_process.kill()
                current_process.wait(timeout=0.1)
            except Exception:
                pass
    
    # Final cleanup before starting
    try:
        subprocess.run(['pkill', '-9', '-f', 'aplay'], capture_output=True, timeout=1)
        subprocess.run(['pkill', '-9', '-f', 'sox'], capture_output=True, timeout=1)
        time.sleep(0.1)
    except Exception:
        pass
    
    # Simple, reliable aplay command without format forcing
    # Let aplay handle format conversion automatically
    cmd = [
        "aplay",
        "-q",
        "-D", device,
        str(wav_path),
    ]
    
    try:
        print(f"PLAY: button={btn_id} file={wav_path} device={device}")
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Verify process started successfully
        time.sleep(0.1)
        if process.poll() is not None:
            print(f"ERROR: aplay failed", file=sys.stderr)
            return current_process
        return process
    except Exception as e:
        print(f"ERROR: Failed to start playback: {e}", file=sys.stderr)
        return current_process


def main() -> int:
    # Global state for configuration reloading
    config_lock = threading.Lock()
    current_config = load_config(DEFAULT_CONFIG_PATH)
    current_profile_cfg = get_active_profile(current_config)
    current_device_cfg = current_config.get("device", {})
    current_button_to_wav = build_button_map(current_profile_cfg)
    
    def reload_config():
        """Reload configuration from file"""
        nonlocal current_config, current_profile_cfg, current_device_cfg, current_button_to_wav
        try:
            with config_lock:
                new_config = load_config(DEFAULT_CONFIG_PATH)
                new_profile_cfg = get_active_profile(new_config)
                new_device_cfg = new_config.get("device", {})
                new_button_to_wav = build_button_map(new_profile_cfg)
                
                current_config = new_config
                current_profile_cfg = new_profile_cfg
                current_device_cfg = new_device_cfg
                current_button_to_wav = new_button_to_wav
                
                print(f"CONFIG RELOADED: {len(current_button_to_wav)} button mappings")
        except Exception as e:
            print(f"Failed to reload config: {e}", file=sys.stderr)

    # Initial configuration
    configured_port = current_device_cfg.get("serial", "/dev/ttyACM0")
    aplay_device = current_device_cfg.get("aplayDevice", "default")

    if not current_button_to_wav:
        print("No button mappings found. Edit config/mappings.json.", file=sys.stderr)

    # Simple state tracking for interruption
    current_process: Optional[subprocess.Popen] = None
    current_button: Optional[int] = None
    
    # Very short debounce for maximum responsiveness
    last_press_ts: Dict[int, float] = {}
    debounce_ms = 50.0  # Increased debounce for cheap arcade buttons

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

    # File watcher thread for configuration reloading
    def watch_config_file():
        """Watch for changes to the configuration file"""
        last_mtime = 0
        while not stop:
            try:
                if DEFAULT_CONFIG_PATH.exists():
                    current_mtime = DEFAULT_CONFIG_PATH.stat().st_mtime
                    if current_mtime > last_mtime and last_mtime > 0:
                        print("Configuration file changed, reloading...")
                        # Add small delay to avoid race conditions with active button presses
                        time.sleep(0.5)
                        reload_config()
                    last_mtime = current_mtime
                time.sleep(1.0)  # Check every second
            except Exception as e:
                print(f"Config watcher error: {e}", file=sys.stderr)
                time.sleep(5.0)  # Wait longer on error

    # Start config watcher thread
    watcher_thread = threading.Thread(target=watch_config_file, daemon=True)
    watcher_thread.start()

    current_port: Optional[str] = None
    backoff_s = 0.5
    print(f"Sound trigger daemon starting. ALSA device='{aplay_device}'")
    print(f"Looking for serial port: {configured_port}")
    print(f"Button mappings: {len(current_button_to_wav)} buttons configured")
    print("Configuration auto-reload enabled")
    
    while not stop:
        # Ensure we have a serial port
        try:
            if not current_port:
                current_port = resolve_serial_port(configured_port)
                if not current_port:
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 1.5, 5.0)
                    continue
                print(f"Opening serial: {current_port}")
            with open_serial(current_port) as ser:
                print("Serial open; trigger loop ready.")
                backoff_s = 0.5
                while not stop:
                    try:
                        line = ser.readline().decode("ascii", errors="ignore")
                    except (serial.SerialException, OSError) as e:
                        # Device likely disconnected; break to outer to re-open
                        print(f"Serial exception ({e}); will re-open.")
                        break
                    except Exception as e:
                        print(f"Unexpected serial error ({e}); will re-open.")
                        break
                    
                    if line:
                        sys.stdout.write(f"SER:{line}")
                        sys.stdout.flush()  # Ensure output is flushed
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

                    # Get current button mapping with thread safety
                    with config_lock:
                        wav_path = current_button_to_wav.get(btn_id)
                    if not wav_path:
                        print(f"No mapping for button {btn_id}")
                        continue

                    # Handle button press with immediate response
                    try:
                        # Get a snapshot of current config to avoid race conditions
                        with config_lock:
                            current_aplay_device = current_device_cfg.get("aplayDevice", "default")
                        
                        # Start new playback (this will interrupt any current playback)
                        current_process = play_wav_interruptible(wav_path, current_aplay_device, current_process, btn_id)
                        current_button = btn_id
                            
                    except Exception as e:
                        print(f"Error handling button {btn_id}: {e}", file=sys.stderr)
        except (serial.SerialException, FileNotFoundError) as exc:
            # Could not open the port; reset and retry
            print(f"Serial open failed on {current_port or configured_port}: {exc}")
        # Reset to force re-resolve next iteration
        current_port = None
        time.sleep(backoff_s)
        backoff_s = min(backoff_s * 1.5, 5.0)

    print("Exiting.")
    if current_process and current_process.poll() is None:
        current_process.terminate()
        try:
            current_process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            current_process.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())