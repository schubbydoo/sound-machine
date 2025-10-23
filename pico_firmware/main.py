# MicroPython firmware for Sound Machine (Pico)
# - 16 buttons active-low -> prints "P,<id>\n" on press
# - 4 LED buttons with random background blink, host override via USB serial:
#     Host sends: "L,<id>,0|1\n"
# Mapping:
# Buttons 1–12 -> GP2..GP13; 13–16 -> GP18..GP21
# LED buttons: 1->GP14, 7->GP15, 9->GP16, 15->GP17

import sys
import time
import urandom
import _thread
import uselect
from machine import Pin

# Button GPIOs
BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
    13: 18, 14: 19, 15: 20, 16: 21,
}

# LED GPIOs (subset of buttons)
# Note: Buttons 9 and 15 LEDs are physically swapped in hardware
LED_BUTTON_TO_PIN = {
    1: 14,
    7: 15,
    9: 17,  # Physical LED for button 9 is on GP17
    15: 16, # Physical LED for button 15 is on GP16
}

# Initialize inputs with pull-ups (active-low switches)
buttons = {btn_id: Pin(gpio, Pin.IN, Pin.PULL_UP) for btn_id, gpio in BUTTON_PINS.items()}

# Initialize LED outputs (default off)
leds = {btn_id: Pin(gpio, Pin.OUT) for btn_id, gpio in LED_BUTTON_TO_PIN.items()}
for pin in leds.values():
    pin.value(0)

# Host overrides: None means background blink controls LED
# True/False forces LED on/off
_led_overrides = {btn_id: None for btn_id in LED_BUTTON_TO_PIN}

# Simple debounce state
_last_state = {btn_id: 1 for btn_id in buttons}  # start high (unpressed)
_last_time_ms = {btn_id: 0 for btn_id in buttons}
DEBOUNCE_MS = 50  # Reduced for better responsiveness

# Background blinker thread for LEDs not overridden
def _blink_worker():
    while True:
        # Randomize per LED not overridden
        for btn_id, pin in leds.items():
            override = _led_overrides.get(btn_id)
            if override is None:
                # random twinkle: small chance to toggle briefly
                if urandom.getrandbits(6) == 0:  # ~1/64 chance each cycle
                    pin.value(1)
                    time.sleep_ms(urandom.getrandbits(5) + 20)  # 20..51 ms
                    pin.value(0)
            else:
                pin.value(1 if override else 0)
        time.sleep_ms(20)

# Start blinker thread
_thread.start_new_thread(_blink_worker, ())

# Parse LED command lines from host and utility commands
def _handle_line(line: str):
    line = line.strip()
    if not line:
        return
    if line.startswith("L,"):
        try:
            _, id_part, state_part = line.split(",", 2)
            btn_id = int(id_part)
            state = int(state_part)
            if btn_id in leds:
                if state == 2:
                    _led_overrides[btn_id] = None
                else:
                    _led_overrides[btn_id] = True if state == 1 else False
        except Exception:
            pass
    elif line == "Q":
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
        for _ in range(2):  # Reduced to avoid blocking
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
    time.sleep_ms(10)  # Slightly longer sleep for stability
