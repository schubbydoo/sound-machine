#!/usr/bin/env python3
"""Simple test script to verify Pico communication"""

import serial
import time
import sys

def test_pico():
    try:
        print("Opening serial port /dev/ttyACM0...")
        ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
        print("Serial port opened successfully")
        
        # Wait for any startup messages
        time.sleep(2)
        
        # Send query command
        print("Sending Q command...")
        ser.write(b'Q\n')
        ser.flush()
        
        # Read response
        time.sleep(0.5)
        response = ser.read(200)
        print(f"Response: {response}")
        
        # Try to read any ongoing output
        print("Reading ongoing output for 5 seconds...")
        start_time = time.time()
        while time.time() - start_time < 5:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"Data: {data}")
            time.sleep(0.1)
        
        ser.close()
        print("Test completed")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pico()

