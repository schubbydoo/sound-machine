#!/usr/bin/env python3
"""
Test LED Controller - Standalone test script for LED control
Tests each button's LED pair to ensure they work
"""
import time
import random

# Try real GPIO first, fall back to simulator
try:
    import RPi.GPIO as GPIO
    REAL_GPIO = True
    print("Using real GPIO")
except ImportError:
    REAL_GPIO = False
    print("GPIO not available - using simulator")

# LED GPIO pins
LED_PINS = {
    "white": 22,
    "green": 27,
    "red": 4,
    "blue": 17,
    "yellow": 23,
}

# Button to color pair mapping
BUTTON_LED_PAIRS = {
    1: ("red", "yellow"),
    2: ("red", "blue"),
    3: ("red", "green"),
    4: ("red", "white"),
    5: ("red", "yellow"),
    6: ("red", "blue"),
    7: ("red", "green"),
    8: ("red", "white"),
    9: ("blue", "yellow"),
    10: ("blue", "red"),
    11: ("blue", "green"),
    12: ("blue", "white"),
    13: ("white", "yellow"),
    14: ("green", "yellow"),
    15: ("white", "green"),
    16: ("white", "red"),
}

def set_led(color, state):
    """Set an LED on or off"""
    if REAL_GPIO:
        try:
            pin = LED_PINS.get(color)
            if pin:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        except Exception as e:
            print(f"ERROR setting {color}: {e}")
    else:
        # Simulator
        status = "ON" if state else "OFF"
        print(f"  [{color.upper()} LED {status}]", end=" ")

def blink_pair(colors, duration=3):
    """Blink a color pair for specified duration"""
    c1, c2 = colors
    print(f"\nBlinking {c1.upper()} and {c2.upper()} for {duration} seconds...")
    end_time = time.time() + duration
    
    while time.time() < end_time:
        # First color
        set_led(c1, True)
        if not REAL_GPIO:
            time.sleep(0.15)
        else:
            time.sleep(random.uniform(0.05, 0.15))
        set_led(c1, False)
        time.sleep(random.uniform(0.1, 0.3))

        # Second color
        set_led(c2, True)
        if not REAL_GPIO:
            time.sleep(0.15)
        else:
            time.sleep(random.uniform(0.05, 0.15))
        set_led(c2, False)
        time.sleep(random.uniform(0.1, 0.3))
    
    print("  Done")

def main():
    # Initialize GPIO if using real hardware
    if REAL_GPIO:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for color, pin in LED_PINS.items():
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
        except Exception as e:
            print(f"Failed to initialize GPIO: {e}")
            return
    
    print("\n=== LED Test ===")
    print("This will test each button's LED pair")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            for btn_id, colors in BUTTON_LED_PAIRS.items():
                print(f"\nButton {btn_id}: ", end="")
                blink_pair(colors, duration=2)
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        # Turn off all LEDs
        print("Turning off all LEDs...")
        for color in LED_PINS:
            set_led(color, False)
        if REAL_GPIO:
            print("Done")

if __name__ == "__main__":
    main()

