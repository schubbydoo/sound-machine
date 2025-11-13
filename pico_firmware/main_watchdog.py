# MicroPython firmware for Sound Machine (Pico) with Watchdog Protection
# - Simple button scanning with automatic watchdog reset
# - If Pico hangs for >8 seconds, it automatically resets
# - Immune to daemon crashes or USB resets

import time
from machine import Pin, WDT

print("Sound Machine Pico firmware starting (watchdog protected)...")

# Enable watchdog - 8 second timeout (will auto-reset if not fed)
wdt = WDT(timeout=8000)
print("Watchdog enabled: 8 second timeout")

# Button GPIOs
BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
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

print("Sound Machine Pico firmware started (WATCHDOG PROTECTED)")
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
        
        # Feed the watchdog every loop to keep it happy
        wdt.feed()
        
        # Periodic status to show we're alive
        loop_count += 1
        if loop_count % 500 == 0:  # Every ~10 seconds
            print(f"Alive: {loop_count} loops (watchdog fed)")
            
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught, continuing...")
        continue
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep_ms(100)
        # Keep feeding watchdog even on error
        wdt.feed()
        continue

