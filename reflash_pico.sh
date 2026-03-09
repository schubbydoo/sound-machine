#!/bin/bash
# Script to reflash Pico firmware after power cycle
# Run this after power cycling the system

PICO_PORT="/dev/ttyACM0"
FIRMWARE="pico_firmware/main.py"
MAX_WAIT=30

echo "Waiting for Pico to appear on $PICO_PORT..."
for i in $(seq 1 $MAX_WAIT); do
    if [ -e "$PICO_PORT" ]; then
        echo "Pico found! Waiting 2 seconds for it to initialize..."
        sleep 2
        break
    fi
    sleep 1
done

if [ ! -e "$PICO_PORT" ]; then
    echo "ERROR: Pico not found on $PICO_PORT after $MAX_WAIT seconds"
    exit 1
fi

echo "Uploading firmware to Pico..."
mpremote connect $PICO_PORT cp $FIRMWARE :main.py

if [ $? -eq 0 ]; then
    echo "✓ Firmware uploaded successfully!"
    echo "Resetting Pico..."
    mpremote connect $PICO_PORT reset
    sleep 2
    echo "✓ Pico should now be running correct firmware"
    echo "Test buttons to verify they work."
else
    echo "✗ Failed to upload firmware. Pico may need to be in bootloader mode."
    echo "If this persists, you may need to:"
    echo "1. Power cycle again"
    echo "2. Or temporarily open enclosure to press BOOTSEL button"
fi



