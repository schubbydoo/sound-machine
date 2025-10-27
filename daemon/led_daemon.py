#!/usr/bin/env python3
"""
LED Daemon - Independent LED control
Reads button press events from named pipe written by audio daemon
"""
import os
import sys
import threading
import time
import random
import stat
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO = None
    GPIO_AVAILABLE = False

# Event FIFO (named pipe) from audio daemon
EVENT_FIFO = Path("/tmp/sound_led_events")

# LED GPIO pins
LED_PINS = {
    "white": int(os.environ.get("LED_WHITE", "22")),
    "green": int(os.environ.get("LED_GREEN", "27")),
    "red": int(os.environ.get("LED_RED", "4")),
    "blue": int(os.environ.get("LED_BLUE", "17")),
    "yellow": int(os.environ.get("LED_YELLOW", "23")),
}

# Button to color pair mapping
BUTTON_LED_PAIRS = {
    1: ("red", "yellow"), 2: ("red", "blue"), 3: ("red", "green"), 4: ("red", "white"),
    5: ("red", "yellow"), 6: ("red", "blue"), 7: ("red", "green"), 8: ("red", "white"),
    9: ("blue", "yellow"), 10: ("blue", "red"), 11: ("blue", "green"), 12: ("blue", "white"),
    13: ("white", "yellow"), 14: ("green", "yellow"), 15: ("white", "green"), 16: ("white", "red"),
}


class LEDController:
    """Controls LED blinking"""
    
    def __init__(self):
        global GPIO_AVAILABLE
        self.current_colors: Optional[Tuple[str, str]] = None
        self.blink_active = False
        self.blink_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.initialized = False
        
        if not GPIO_AVAILABLE:
            print("LED: GPIO not available - simulation mode")
            return
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for color, pin in LED_PINS.items():
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            self.initialized = True
        except Exception as e:
            print(f"LED: GPIO init failed: {e}")
            GPIO_AVAILABLE = False
    
    def set_led(self, color: str, state: bool) -> None:
        """Set an LED on or off"""
        if not self.initialized or not GPIO_AVAILABLE:
            return
        pin = LED_PINS.get(color)
        if pin:
            try:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            except Exception:
                pass
    
    def start_blink(self, colors: Tuple[str, str]) -> None:
        """Start blinking the specified color pair"""
        with self.lock:
            self.stop_blink()
            self.current_colors = colors
            self.blink_active = True
            
            def blink_loop():
                c1, c2 = self.current_colors
                while self.blink_active:
                    self.set_led(c1, True)
                    time.sleep(random.uniform(0.05, 0.15))
                    self.set_led(c1, False)
                    time.sleep(random.uniform(0.1, 0.3))
                    
                    self.set_led(c2, True)
                    time.sleep(random.uniform(0.05, 0.15))
                    self.set_led(c2, False)
                    time.sleep(random.uniform(0.1, 0.3))
            
            self.blink_thread = threading.Thread(target=blink_loop, daemon=True)
            self.blink_thread.start()
    
    def stop_blink(self) -> None:
        """Stop blinking and turn off all LEDs"""
        with self.lock:
            self.blink_active = False
            if self.initialized:
                for color in LED_PINS:
                    self.set_led(color, False)
    
    def cleanup(self) -> None:
        """Cleanup GPIO resources"""
        self.stop_blink()


def main():
    # Create named pipe if it doesn't exist
    try:
        if EVENT_FIFO.exists():
            if not stat.S_ISFIFO(EVENT_FIFO.stat().st_mode):
                print(f"ERROR: {EVENT_FIFO} exists but is not a named pipe", file=sys.stderr)
                sys.exit(1)
        else:
            os.mkfifo(str(EVENT_FIFO), 0o666)
            print(f"LED Daemon: Created FIFO at {EVENT_FIFO}")
    except FileExistsError:
        # Another process created it
        pass
    except Exception as e:
        print(f"ERROR: Failed to create FIFO: {e}", file=sys.stderr)
        sys.exit(1)
    
    controller = LEDController()
    last_button_time = 0
    TIMEOUT_SECONDS = 20.0
    
    print(f"LED Daemon: Monitoring {EVENT_FIFO}")
    print(f"LED Daemon: Timeout {TIMEOUT_SECONDS}s")
    
    try:
        while True:
            try:
                # Open FIFO for reading (blocks until audio daemon opens it for writing)
                print("LED Daemon: Waiting for events from audio daemon...", file=sys.stderr)
                with open(str(EVENT_FIFO), 'r') as fifo:
                    while True:
                        current_time = time.time()
                        
                        # Check for timeout
                        if last_button_time > 0 and (current_time - last_button_time) > TIMEOUT_SECONDS:
                            controller.stop_blink()
                            last_button_time = 0
                        
                        # Read button ID from pipe (blocks until data arrives)
                        line = fifo.readline()
                        if not line:
                            # EOF - audio daemon closed the pipe, reconnect
                            print("LED Daemon: Audio daemon disconnected, waiting for reconnection...", file=sys.stderr)
                            break
                        
                        try:
                            button_id = int(line.strip())
                            colors = BUTTON_LED_PAIRS.get(button_id)
                            if colors:
                                print(f"LED: Button {button_id} -> Blinking {colors[0]}/{colors[1]}")
                                sys.stdout.flush()
                                controller.start_blink(colors)
                                last_button_time = current_time
                        except (ValueError, KeyError):
                            pass
                        
            except FileNotFoundError:
                print("LED Daemon: FIFO not found, waiting...", file=sys.stderr)
                time.sleep(1.0)
            except Exception as e:
                print(f"LED Daemon error: {e}", file=sys.stderr)
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()
        # Clean up FIFO
        try:
            if EVENT_FIFO.exists():
                EVENT_FIFO.unlink()
        except Exception:
            pass
        print("LED Daemon: Exiting")


if __name__ == "__main__":
    main()
