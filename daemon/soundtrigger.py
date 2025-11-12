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

# LED daemon communication via named pipe
LED_FIFO = Path("/tmp/sound_led_events")

PRESS_RE = re.compile(r"^P,(\d{1,2})\s*$")

DEFAULT_CONFIG_PATH = Path(
    os.environ.get("SOUND_MACHINE_CONFIG", "/home/soundconsole/sound-machine/config/mappings.json")
)

# No event file needed - direct function calls


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


# LED functions removed - no LEDs on this switch board


def check_audio_device(device: str) -> bool:
    """Check if audio device is available"""
    try:
        # Quick check: try to query the device
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
                # Try opening the FIFO for writing with a timeout
                # Use non-blocking mode first to check if reader is ready
                try:
                    fd = os.open(str(LED_FIFO), os.O_WRONLY | os.O_NONBLOCK)
                    os.write(fd, f"{btn_id}\n".encode())
                    os.close(fd)
                except (BlockingIOError, OSError):
                    # Reader might not be ready - try one blocking attempt
                    # If this hangs, the daemon thread will still exit when soundtrigger exits
                    try:
                        with open(str(LED_FIFO), 'w') as fifo:
                            fifo.write(f"{btn_id}\n")
                            fifo.flush()
                    except (OSError, BrokenPipeError):
                        pass  # LED daemon not listening
        except Exception:
            # Any other error - silently ignore
            pass
    
    # Start write in background thread so it never blocks the main audio daemon thread
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
    
    # Check if audio device is available before attempting playback
    if not check_audio_device(device):
        print(f"ERROR: Audio device '{device}' not available", file=sys.stderr)
        return None
    
    # Force kill any stuck process aggressively
    if current_process:
        # Check if it's been running too long (stuck)
        try:
            # Try to see if it's responding
            if current_process.poll() is None:
                # Process still running - check if it's stuck
                try:
                    current_process.terminate()
                    current_process.wait(timeout=0.5)  # Give it half a second
                except subprocess.TimeoutExpired:
                    # Process is stuck - kill it aggressively
                    print(f"WARN: Killing stuck audio process", file=sys.stderr)
                    current_process.kill()
                    current_process.wait(timeout=0.5)
                except Exception as e:
                    print(f"WARN: Error killing process: {e}", file=sys.stderr)
        except Exception as e:
            print(f"WARN: Error checking process: {e}", file=sys.stderr)
    
    # Simple, reliable aplay command - files should already be in correct format
    cmd = [
        "aplay",
        "-q",
        "-D", device,
        str(wav_path),
    ]
    
    try:
        print(f"PLAY: button={btn_id} file={wav_path} device={device}")
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Check if process started successfully
        time.sleep(0.1)  # Brief check
        if process.poll() is not None:
            print(f"ERROR: aplay exited immediately", file=sys.stderr)
            return None
        
        return process
    except Exception as e:
        print(f"ERROR: Failed to start playback: {e}", file=sys.stderr)
        return None


def main() -> int:
    # Global state for configuration reloading
    config_lock = threading.Lock()
    
    # Load initial configuration
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
    
    # Initialize LED controller if available - DISABLED
    # LED code appears to cause crashes - keeping disabled for now
    # if led_controller:
    #     try:
    #         led_gpio = current_device_cfg.get("ledGPIO", {})
    #         if led_gpio:
    #             led_controller.init(led_gpio)
    #     except Exception as e:
    #         print(f"LED initialization failed (LEDs will not work): {e}")

    if not current_button_to_wav:
        print("No button mappings found. Edit config/mappings.json.", file=sys.stderr)

    # Simple state tracking for interruption
    current_process: Optional[subprocess.Popen] = None
    current_button: Optional[int] = None
    
    # Increased debounce for cheap arcade buttons to prevent rapid-fire presses
    last_press_ts: Dict[int, float] = {}
    debounce_ms = 200.0  # Increased from 50ms to 200ms for better debouncing
    
    def cleanup_debounce_dict():
        """Remove old entries from debounce dict to prevent memory growth"""
        nonlocal last_press_ts
        current_time = time.time() * 1000.0
        # Remove entries older than 60 seconds
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
    
    # Audio device health monitor thread
    def monitor_audio_device():
        """Periodically check if audio device is still available"""
        last_check = time.time()
        while not stop:
            try:
                # Check every 2 seconds
                if time.time() - last_check >= 2.0:
                    if not check_audio_device(aplay_device):
                        print(f"WARN: Audio device '{aplay_device}' disappeared", file=sys.stderr)
                    last_check = time.time()
                time.sleep(0.5)
            except Exception as e:
                print(f"Audio monitor error: {e}", file=sys.stderr)
                time.sleep(2.0)
    
    audio_monitor_thread = threading.Thread(target=monitor_audio_device, daemon=True)
    audio_monitor_thread.start()

    # Audio playback monitor thread - watches for when audio finishes and sends LED stop signal
    def monitor_audio_playback():
        """Monitor the current audio process and send LED stop signal when it finishes"""
        nonlocal current_process, current_button
        last_signaled_process_id = None
        while not stop:
            try:
                # Check if we have an active process that just finished
                if current_process and current_process.poll() is not None:
                    # Process has exited - send stop signal to LED daemon (only once per process)
                    current_process_id = id(current_process)
                    if last_signaled_process_id != current_process_id:
                        print(f"PLAY_END: Audio finished for button {current_button}")
                        send_led_stop_signal()
                        last_signaled_process_id = current_process_id
                else:
                    # Process is still running or None - reset the signal tracker
                    # This allows sending a signal when the NEXT process finishes
                    if current_process:
                        last_signaled_process_id = None
                time.sleep(0.1)  # Check frequently for immediate response
            except Exception as e:
                print(f"Playback monitor error: {e}", file=sys.stderr)
                time.sleep(0.5)
    
    playback_monitor_thread = threading.Thread(target=monitor_audio_playback, daemon=True)
    playback_monitor_thread.start()

    current_port: Optional[str] = None
    backoff_s = 0.5
    print(f"Sound trigger daemon starting. ALSA device='{aplay_device}'")
    print(f"Looking for serial port: {configured_port}")
    print(f"Button mappings: {len(current_button_to_wav)} buttons configured")
    print("Configuration auto-reload enabled")
    
    # Set audio volume to 100%
    try:
        subprocess.run(['amixer', '-c', '0', 'set', 'Speaker', '100%'], capture_output=True, timeout=2)
        print("Audio volume set to 100%")
    except Exception as e:
        print(f"Could not set audio volume: {e}")
    
    while not stop:
        # Ensure we have a serial port
        try:
            if not current_port:
                current_port = resolve_serial_port(configured_port)
                if not current_port:
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 1.5, 5.0)
                    continue
                print(f"Opening serial: {current_port}", flush=True)
            try:
                with open_serial(current_port) as ser:
                    print("Serial open; trigger loop ready.", flush=True)
                    backoff_s = 0.5
                    while not stop:
                        try:
                            line = ser.readline().decode("ascii", errors="ignore")
                        except (serial.SerialException, OSError) as e:
                            # Device likely disconnected; break to outer to re-open
                            print(f"Serial exception ({e}); will re-open.", flush=True)
                            current_port = None  # Force re-open attempt
                            break
                        except Exception as e:
                            print(f"Unexpected serial error ({e}); will re-open.", flush=True)
                            current_port = None  # Force re-open attempt
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
                        
                        # Cleanup debounce dict periodically to prevent memory growth
                        if len(last_press_ts) > 20:
                            cleanup_debounce_dict()

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
                            send_button_event_to_led_daemon(btn_id) # Send LED event immediately
                                
                        except Exception as e:
                            print(f"Error handling button {btn_id}: {e}", file=sys.stderr, flush=True)
            except (serial.SerialException, FileNotFoundError) as exc:
                # Could not open the port; reset and retry
                print(f"Serial open failed on {current_port or configured_port}: {exc}", flush=True)
                backoff_s = min(backoff_s * 1.5, 5.0)
            except Exception as e:
                print(f"Unexpected error in serial handling: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc(file=sys.stderr)
                backoff_s = min(backoff_s * 1.5, 5.0)
        except Exception as e:
            print(f"Unexpected error in main daemon loop: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            backoff_s = min(backoff_s * 1.5, 5.0)
        
        # ALWAYS reset port after each iteration to force fresh connection
        current_port = None
        time.sleep(backoff_s)

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