#!/usr/bin/env python3
"""
Serial Broadcaster - Reads from Pico serial port and broadcasts to multiple daemons
Ensures both audio and LED daemons receive all button presses
"""
import serial
import sys
import time
from pathlib import Path

SERIAL_PORT = "/dev/ttyACM0"
BAUDRATE = 115200
TIMEOUT = 1.0

def read_serial_and_broadcast():
    """Read from serial port and broadcast to stdout and LED daemon"""
    try:
        ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        print(f"Reading from {SERIAL_PORT}", file=sys.stderr)
        
        while True:
            try:
                line = ser.readline().decode("ascii", errors="ignore")
                if line:
                    # Send to stdout (audio daemon will read this)
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    
            except (serial.SerialException, OSError) as e:
                print(f"Serial error: {e}", file=sys.stderr)
                time.sleep(1.0)
                break
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        time.sleep(1.0)

if __name__ == "__main__":
    while True:
        read_serial_and_broadcast()


