#!/usr/bin/env python3
"""
Sound Machine trigger daemon
- Reads Pico USB CDC (serial) lines in the format: P,<id>\n
- Plays mapped WAV via aplay
- Sends LED override: L,<id>,1 during playback, then L,<id>,0

This is a minimal working stub intended for development bring-up.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
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
    return serial.Serial(port=port, baudrate=baudrate, timeout=timeout)


def resolve_serial_port(preferred: str) -> Optional[str]:
    """Return a usable serial device path.

    Tries the configured path first; if missing, tries stable by-id links;
    finally falls back to the first /dev/ttyACM* discovered.
    """
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


def send_led(ser: serial.Serial, button_id: int, on: bool) -> None:
    ser.write(f"L,{button_id},{1 if on else 0}\n".encode("ascii"))
    ser.flush()


def clear_led_override(ser: serial.Serial, button_id: int) -> None:
    # State=2 means "clear override" -> resume background blinking on Pico
    ser.write(f"L,{button_id},2\n".encode("ascii"))
    ser.flush()


def play_wav(wav_path: Path, device: str) -> int:
    if not wav_path.exists():
        print(f"WAV not found: {wav_path}", file=sys.stderr)
        return 1
    cmd = [
        "aplay",
        "-q",
        "-D",
        device,
        str(wav_path),
    ]
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print("ERROR: 'aplay' not found. Install 'alsa-utils'.", file=sys.stderr)
        return 1


def main() -> int:
    config = load_config(DEFAULT_CONFIG_PATH)
    profile_cfg = get_active_profile(config)

    device_cfg = config.get("device", {})
    configured_port = device_cfg.get("serial", "/dev/ttyACM0")
    aplay_device = device_cfg.get("aplayDevice", "default")

    button_to_wav = build_button_map(profile_cfg)
    if not button_to_wav:
        print("No button mappings found. Edit config/mappings.json.", file=sys.stderr)

    # Basic debounce window per button
    last_press_ts: Dict[int, float] = {}
    debounce_ms = 80.0

    stop = False

    def handle_sig(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    current_port: Optional[str] = None
    backoff_s = 0.5
    print(f"Sound trigger daemon starting. ALSA device='{aplay_device}'")
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
                    except serial.SerialException:
                        # Device likely disconnected; break to outer to re-open
                        print("Serial exception; will re-open.")
                        break
                    if line:
                        sys.stdout.write(f"SER:{line}")
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

                    wav_path = button_to_wav.get(btn_id)
                    if not wav_path:
                        print(f"No mapping for button {btn_id}")
                        continue

                    try:
                        print(f"PLAY: button={btn_id} file={wav_path} device={aplay_device}")
                        send_led(ser, btn_id, True)
                        rc = play_wav(wav_path, aplay_device)
                        if rc != 0:
                            print(f"aplay exited with code {rc}")
                    finally:
                        clear_led_override(ser, btn_id)
        except (serial.SerialException, FileNotFoundError) as exc:
            # Could not open the port; reset and retry
            print(f"Serial open failed on {current_port or configured_port}: {exc}")
        # Reset to force re-resolve next iteration
        current_port = None
        time.sleep(backoff_s)
        backoff_s = min(backoff_s * 1.5, 5.0)

    print("Exiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
