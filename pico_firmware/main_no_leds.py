# MicroPython firmware for Sound Machine (Pico) - No LEDs version
# - 16 buttons active-low -> prints "P,<id>\n" on press
# Mapping: Buttons 1–12 -> GP2..GP13; 13–16 -> GP18..GP21

import sys
import time
import uselect
from machine import Pin

print("Sound Machine Pico firmware starting (no LEDs)...")

# Button GPIOs
BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
    13: 18, 14: 19, 15: 20, 16: 21,
}

# Initialize inputs with pull-ups (active-low switches)
buttons = {btn_id: Pin(gpio, Pin.IN, Pin.PULL_UP) for btn_id, gpio in BUTTON_PINS.items()}

# Simple debounce state
_last_state = {btn_id: 1 for btn_id in buttons}  # start high (unpressed)
_last_time_ms = {btn_id: 0 for btn_id in buttons}
DEBOUNCE_MS = 50

# Handle host commands
def _handle_line(line: str):
    line = line.strip()
    if line == "Q":
        # Emit a compact state snapshot: S,<id>,<0|1> ... (0=pressed,1=idle)
        try:
            parts = []
            for btn_id, pin in buttons.items():
                pressed = 0 if pin.value() == 0 else 1
                parts.append("%d,%d" % (btn_id, pressed))
            sys.stdout.write("S," + " ".join(parts) + "\n")
            sys.stdout.flush()
        except Exception:
            pass

# Non-blocking host command reader
try:
    _poll = uselect.poll()
    _poll.register(sys.stdin, uselect.POLLIN)
except Exception:
    _poll = None

def _read_host_commands():
    try:
        if not _poll:
            return
        for _ in range(2):
            events = _poll.poll(0)
            if not events:
                break
            line = sys.stdin.readline()
            if isinstance(line, bytes):
                line = line.decode('utf-8', 'ignore')
            if line:
                _handle_line(line)
    except Exception:
        pass

# Main loop: scan buttons, report presses
print("Sound Machine Pico firmware started")
while True:
    now_ms = time.ticks_ms()
    # Read a potential host command each cycle
    _read_host_commands()

    for btn_id, pin in buttons.items():
        state = 1 if pin.value() else 0  # 1=idle(high), 0=pressed(low)
        if state != _last_state[btn_id]:
            _last_state[btn_id] = state
            if state == 0:  # Button pressed
                # Check debounce
                if time.ticks_diff(now_ms, _last_time_ms[btn_id]) > DEBOUNCE_MS:
                    _last_time_ms[btn_id] = now_ms
                    # Emit press event
                    try:
                        sys.stdout.write("P,{}\n".format(btn_id))
                        sys.stdout.flush()
                    except Exception:
                        pass
    time.sleep_ms(10)
