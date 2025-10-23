# Diagnostic MicroPython firmware for Sound Machine (Pico)
# - Shows GPIO states for all button pins
# - Helps debug wiring issues

import time
from machine import Pin

print("Sound Machine Pico DIAGNOSTIC firmware starting...")

# Button GPIOs
BUTTON_PINS = {
    1: 2,  2: 3,  3: 4,  4: 5,
    5: 6,  6: 7,  7: 8,  8: 9,
    9: 10, 10: 11, 11: 12, 12: 13,
    13: 18, 14: 19, 15: 20, 16: 21,
}

# Initialize inputs with pull-ups (active-low switches)
buttons = {btn_id: Pin(gpio, Pin.IN, Pin.PULL_UP) for btn_id, gpio in BUTTON_PINS.items()}

print("Button mapping:")
for btn_id, gpio in BUTTON_PINS.items():
    print(f"  Button {btn_id} -> GPIO {gpio}")

print("GPIO states (1=idle/high, 0=pressed/low):")
print("Press buttons to see state changes...")

loop_count = 0
last_states = {btn_id: 1 for btn_id in buttons}

while True:
    try:
        # Check all button states
        current_states = {}
        for btn_id, pin in buttons.items():
            current_states[btn_id] = 1 if pin.value() else 0
        
        # Print state changes
        for btn_id in buttons:
            if current_states[btn_id] != last_states[btn_id]:
                print(f"Button {btn_id}: {last_states[btn_id]} -> {current_states[btn_id]}")
                last_states[btn_id] = current_states[btn_id]
        
        # Print all states every 100 loops (every 2 seconds)
        loop_count += 1
        if loop_count % 100 == 0:
            states_str = " ".join([f"{btn_id}:{current_states[btn_id]}" for btn_id in sorted(buttons.keys())])
            print(f"States: {states_str}")
        
        time.sleep_ms(20)  # 50Hz polling
            
    except KeyboardInterrupt:
        print("KeyboardInterrupt caught, continuing...")
        continue
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep_ms(100)
        continue
