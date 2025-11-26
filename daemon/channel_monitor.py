#!/usr/bin/env python3
"""
Channel Monitor Daemon
- Monitors GPIO pins 22, 23, 24, 25 for the rotary switch position.
- Updates the 'active_channel' in the SQLite database.
"""
import time
import sys
import sqlite3
import signal
from pathlib import Path

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO = None
    GPIO_AVAILABLE = False
    print("WARNING: RPi.GPIO not found. Running in simulation mode.", file=sys.stderr)

# Configuration
DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')
POLL_INTERVAL = 0.1  # Check every 100ms
DEBOUNCE_TIME = 0.2

# Channel to GPIO mapping
CHANNEL_PINS = {
    1: 22,
    2: 23,
    3: 24,
    4: 25
}

running = True

def signal_handler(sig, frame):
    global running
    running = False

def init_gpio():
    if not GPIO_AVAILABLE:
        return
    
    GPIO.setmode(GPIO.BCM)
    for pin in CHANNEL_PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def get_active_hardware_channel():
    if not GPIO_AVAILABLE:
        # Simulation: Default to 1
        return 1
        
    # Check which pin is LOW (Active)
    # If multiple are LOW (switching/short), prioritize lower number or stick to last?
    # Requirement: "One GPIO pin represents one channel"
    
    active = None
    for channel, pin in CHANNEL_PINS.items():
        if GPIO.input(pin) == GPIO.LOW:
            active = channel
            break # Priority to lower channels if multiple pressed? Or should we handle error?
            
    return active

def update_db_active_channel(channel):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", 
            ("active_channel", str(channel))
        )
        conn.commit()
        conn.close()
        # print(f"Channel set to {channel}")
    except Exception as e:
        print(f"Error updating DB: {e}", file=sys.stderr)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    init_gpio()
    
    last_channel = None
    
    print("Channel Monitor started.")
    
    while running:
        current_channel = get_active_hardware_channel()
        
        # If no channel is detected (e.g. between clicks), ignore or keep last?
        # Ideally, we keep the last known valid channel.
        if current_channel is not None and current_channel != last_channel:
            # Debounce check could go here if needed, but 100ms poll is slow enough
            update_db_active_channel(current_channel)
            last_channel = current_channel
            
        time.sleep(POLL_INTERVAL)
    
    if GPIO_AVAILABLE:
        GPIO.cleanup()
    print("Channel Monitor stopped.")

if __name__ == "__main__":
    main()

