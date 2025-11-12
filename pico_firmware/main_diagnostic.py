# Diagnostic MicroPython firmware for Sound Machine (Pico)
# - Check GPIO states without requiring button presses
# - Useful for verifying the Pico works before wiring buttons

import time
from machine import Pin

print("Sound Machine Pico firmware starting (diagnostic version)...")

# Button GPIOs - just initialize as inputs to test
BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
    13: 18, 14: 19, 15: 20, 16: 21,
}

print(f"Initializing {len(BUTTON_PINS)} GPIO pins...")
try:
    buttons = {}
    for btn_id, gpio in BUTTON_PINS.items():
        try:
            pin = Pin(gpio, Pin.IN, Pin.PULL_UP)
            buttons[btn_id] = pin
            print(f"  ✓ Button {btn_id:2d} on GPIO {gpio:2d} initialized")
        except Exception as e:
            print(f"  ✗ Button {btn_id:2d} on GPIO {gpio:2d} FAILED: {e}")
    print(f"Successfully initialized {len(buttons)}/{len(BUTTON_PINS)} pins")
except Exception as e:
    print(f"Initialization error: {e}")
    import sys
    sys.exit(1)

print("\nRunning GPIO state monitor...")
print("(This test will show GPIO values. Press Ctrl+C to stop)\n")

loop_count = 0
try:
    while True:
        loop_count += 1
        
        # Every 50 loops (~1 second), print status
        if loop_count % 50 == 0:
            states = []
            for btn_id in sorted(buttons.keys()):
                pin = buttons[btn_id]
                val = pin.value()
                states.append(f"{btn_id}:{val}")
            print(f"Loop {loop_count:6d}: {' '.join(states)}")
        
        time.sleep_ms(20)
        
except KeyboardInterrupt:
    print("\nDiagnostic stopped by user")
except Exception as e:
    print(f"Runtime error: {e}")
    import traceback
    traceback.print_exc()
