# Safe MicroPython firmware for Sound Machine (Pico)
# - Uses GPIO pins that are definitely safe
# - Avoids GPIO 2-3 which are used for QSPI flash on RP2040
# Mapping: Buttons 1–12 -> GP5..GP16; 13–16 -> GP18..GP21 (skip GP2,GP3,GP4)

import time
from machine import Pin

print("Sound Machine Pico firmware starting (safe version)...")

# Safer GPIO mapping - avoiding GPIO 2-3 (QSPI) and GPIO 4 (might have other uses)
BUTTON_PINS = {
    1: 5,  2: 6,  3: 7,  4: 8,
    5: 9,  6: 10, 7: 11, 8: 12,
    9: 13, 10: 14, 11: 15, 12: 16,
    13: 18, 14: 19, 15: 20, 16: 21,
}

# Initialize inputs with pull-ups (active-low switches)
print("Initializing GPIO pins...")
try:
    buttons = {btn_id: Pin(gpio, Pin.IN, Pin.PULL_UP) for btn_id, gpio in BUTTON_PINS.items()}
    print(f"✓ Successfully initialized {len(buttons)} GPIO pins")
except Exception as e:
    print(f"✗ Failed to initialize pins: {e}")
    import sys
    sys.exit(1)

# Simple debounce state
_last_state = {btn_id: 1 for btn_id in buttons}  # start high (unpressed)
_last_time_ms = {btn_id: 0 for btn_id in buttons}
DEBOUNCE_MS = 100  # Longer debounce for cheap buttons

print("Sound Machine Pico firmware started (safe GPIO configuration)")
print("Button mapping:")
for btn_id, gpio in sorted(BUTTON_PINS.items()):
    print(f"  Button {btn_id:2d} -> GPIO {gpio:2d}")

loop_count = 0
while True:
    try:
        now_ms = time.ticks_ms()
        
        for btn_id, pin in buttons.items():
            state = 1 if pin.value() else 0  # 1=idle(high), 0=pressed(low)
            if state != _last_state[btn_id]:
                _last_state[btn_id] = state
                if state == 0:  # Button pressed
                    # Check debounce
                    if time.ticks_diff(now_ms, _last_time_ms[btn_id]) > DEBOUNCE_MS:
                        _last_time_ms[btn_id] = now_ms
                        # Emit press event
                        print(f"P,{btn_id}")
        
        time.sleep_ms(20)  # 50Hz polling
        
        # Periodic status to show we're alive
        loop_count += 1
        if loop_count % 500 == 0:  # Every ~10 seconds
            print(f"Alive: {loop_count} loops")
            
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught, continuing...")
        continue
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep_ms(100)
        continue

