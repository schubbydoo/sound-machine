#!/usr/bin/env python3
"""
Test Event System - Simulates button press events for LED testing
"""
import time
import json

EVENT_FILE = "/tmp/sound_trigger_events.json"

def send_event(event_type, button_id=None):
    """Send an event to the LED controller"""
    event = {
        "type": event_type,
        "timestamp": time.time()
    }
    if button_id:
        event["button_id"] = button_id
    
    with open(EVENT_FILE, 'w') as f:
        json.dump(event, f)
    print(f"Sent: {event}")

def main():
    print("\n=== Event Test ===")
    print("This will send test events to the LED controller")
    print("Make sure the LED daemon is running\n")
    
    time.sleep(2)
    
    # Test a few button presses
    buttons_to_test = [1, 2, 3, 13, 14, 15]
    
    for btn_id in buttons_to_test:
        print(f"\nTesting button {btn_id}...")
        send_event("button_pressed", btn_id)
        time.sleep(3)
    
    print("\n\nTest complete!")

if __name__ == "__main__":
    main()




