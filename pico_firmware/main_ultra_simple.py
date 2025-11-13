# Ultra-Simple Pico Firmware - Bulletproof
# Just reads buttons and prints, nothing else

from machine import Pin
import time

BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
    13: 18, 14: 19, 15: 20, 16: 21,
}

buttons = {btn_id: Pin(gpio, Pin.IN, Pin.PULL_UP) for btn_id, gpio in BUTTON_PINS.items()}
_last_state = {btn_id: 1 for btn_id in buttons}
_last_time_ms = {btn_id: 0 for btn_id in buttons}
DEBOUNCE_MS = 100

print("OK")

while True:
    now_ms = time.ticks_ms()
    for btn_id, pin in buttons.items():
        state = 1 if pin.value() else 0
        if state != _last_state[btn_id]:
            _last_state[btn_id] = state
            if state == 0 and time.ticks_diff(now_ms, _last_time_ms[btn_id]) > DEBOUNCE_MS:
                _last_time_ms[btn_id] = now_ms
                print(f"P,{btn_id}")
    time.sleep_ms(20)

