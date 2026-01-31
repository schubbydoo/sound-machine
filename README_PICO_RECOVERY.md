# Pico Firmware Recovery

## Problem
The Pico firmware became corrupted after plugging in power while the system was running. The Pico is stuck in a loop and not detecting button presses.

## Solution

### Option 1: Automatic Recovery (Recommended)
After power cycling the system (unplug battery, wait 10 seconds, plug back in), run:

```bash
cd /home/soundconsole/sound-machine
./reflash_pico.sh
```

This will automatically:
1. Wait for the Pico to appear
2. Upload the correct firmware
3. Reset the Pico

### Option 2: Manual Recovery
If automatic recovery doesn't work:

1. **Power cycle the system** (unplug battery, wait 10 seconds, plug back in)

2. **Wait for Pico to initialize** (about 5-10 seconds)

3. **Upload firmware manually:**
   ```bash
   cd /home/soundconsole/sound-machine
   mpremote connect /dev/ttyACM0 cp pico_firmware/main.py :main.py
   mpremote connect /dev/ttyACM0 reset
   ```

4. **Test buttons** - they should all work now

### Option 3: Bootloader Mode (If above fails)
If the Pico still won't respond, you may need to:
1. Temporarily open the enclosure
2. Hold the BOOTSEL button on the Pico
3. While holding BOOTSEL, power cycle the system
4. Release BOOTSEL after 2 seconds
5. The Pico will appear as a USB mass storage device
6. Copy `pico_firmware/main.py` to the Pico's drive as `main.py`
7. Power cycle again

## Prevention
To prevent this in the future:
- Avoid plugging in power while the system is running
- If you must plug in power, do it when the system is off
- Consider adding a power management circuit to handle hot-plugging safely



