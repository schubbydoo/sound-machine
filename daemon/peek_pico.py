#!/usr/bin/env python3
"""
Peek Pico serial for presses and optionally toggle LED.
Usage examples:
  python3 daemon/peek_pico.py --port /dev/ttyACM0
  python3 daemon/peek_pico.py --port /dev/ttyACM0 --led 7:on
"""
import argparse
import sys
from typing import Tuple

try:
    import serial
except Exception as exc:
    print(f"ERROR: pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)


def parse_led(arg: str) -> Tuple[int, bool]:
    try:
        btn_str, state_str = arg.split(":", 1)
        btn_id = int(btn_str)
        on = state_str.strip().lower() in {"1", "on", "true", "yes"}
        return btn_id, on
    except Exception:
        raise argparse.ArgumentTypeError("--led must be like '7:on' or '7:off'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0", help="Serial port, e.g. /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200, help="Baudrate")
    ap.add_argument("--led", type=parse_led, help="Send LED override 'id:on|off' and exit")
    args = ap.parse_args()

    if args.led:
        btn_id, on = args.led
        with serial.Serial(args.port, args.baud, timeout=1.0) as ser:
            ser.write(f"L,{btn_id},{1 if on else 0}\n".encode("ascii"))
            ser.flush()
        print(f"LED {btn_id} -> {'ON' if on else 'OFF'} sent")
        return 0

    print(f"Reading from {args.port} @ {args.baud} baud. Press Ctrl+C to stop.")
    try:
        with serial.Serial(args.port, args.baud, timeout=0.5) as ser:
            while True:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line:
                    print(f"SERIAL: {line}")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
