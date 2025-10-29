# LED Control System Documentation

## Quick Navigation

Start here based on what you need:

### 🚀 **Just Want to Get Started?**
→ Read: [`LED_QUICK_START.txt`](LED_QUICK_START.txt)

### 📋 **What Changed in the Code?**
→ Read: [`CHANGES_SUMMARY.txt`](CHANGES_SUMMARY.txt)

### 🔧 **Implementation Details**
→ Read: [`LED_IMPLEMENTATION_SUMMARY.md`](LED_IMPLEMENTATION_SUMMARY.md)

### ✅ **Status & Verification**
→ Read: [`IMPLEMENTATION_COMPLETE.md`](IMPLEMENTATION_COMPLETE.md)

### 📖 **Complete Technical Documentation**
→ Read: [`docs/LED_CONTROL.md`](docs/LED_CONTROL.md)

### 🔌 **GPIO Wiring Reference**
→ Read: [`docs/GPIO_PINOUT.md`](docs/GPIO_PINOUT.md)

---

## System Overview

### What It Does

Your glass skull LED lights now respond to button presses and audio playback:

1. **At Rest**: LEDs gently pulse (breathing effect) every 5 seconds
2. **Button Press**: LEDs flash rapidly (on/off at 100ms intervals)
3. **Audio Stops**: LEDs return to gentle pulsing
4. **New Button During Playback**: Flash sequence restarts

### Hardware

- **GPIO Pin**: 18 (on Raspberry Pi Zero GPIO header, physical pin 12)
- **Connection**: Just 2 wires (signal + ground)
- **Compatibility**: Works with any LED circuit that responds to PWM signals

### Key Features

✨ **Simple**: Single GPIO pin instead of 5 separate LEDs  
✨ **Autonomous**: LED daemon works independently from audio  
✨ **Reliable**: State machine instead of timeouts  
✨ **Responsive**: Immediate feedback on button press  
✨ **Customizable**: Easy to adjust timings and GPIO pin  

---

## Testing Checklist

### Without Hardware (Simulation Mode)

```bash
# Terminal 1
python3 daemon/led_daemon.py

# Terminal 2
echo "1" > /tmp/sound_led_events    # Should show: "FLASHING"
sleep 2
echo "0" > /tmp/sound_led_events    # Should show: "IDLE"
```

✅ **Expected**: See FLASHING and IDLE messages in Terminal 1

### With Hardware (After Wiring)

```bash
# Terminal 1
python3 daemon/led_daemon.py

# Terminal 2
python3 daemon/soundtrigger.py

# Then: Press buttons on Pico
```

✅ **Expected**: 
- LEDs flash when you press any button
- LEDs stop and pulse after audio finishes
- Pressing a new button restarts the flash

---

## Hardware Setup (5 minutes)

1. **Locate** GPIO 18 (Pin 12) on the Raspberry Pi Zero GPIO header
2. **Locate** Ground pin (Pin 9)
3. **Connect** Pin 12 → LED switch signal input
4. **Connect** Pin 9 → LED circuit ground
5. **Done!** Ready for testing

[Detailed wiring diagram in `docs/GPIO_PINOUT.md`]

---

## Configuration

### Change GPIO Pin

```bash
export LED_GPIO=12    # or 13, 19, 26
python3 daemon/led_daemon.py
```

### Adjust Pulsing Speed

Edit `daemon/led_daemon.py`, line 33:
```python
PULSE_CYCLE_SECONDS = 5.0  # Change to 3.0 for faster
```

### Adjust Flash Timing

Edit `daemon/led_daemon.py`, lines 34-35:
```python
FLASH_ON_MS = 100   # 100ms on
FLASH_OFF_MS = 100  # 100ms off
```

### Adjust Pulsing Brightness

Edit `daemon/led_daemon.py`, lines 36-37:
```python
IDLE_MIN_PWM = 20   # 20% brightness at dimmest
IDLE_MAX_PWM = 100  # 100% brightness at brightest
```

---

## Files Changed

| File | Change | Impact |
|------|--------|--------|
| `daemon/led_daemon.py` | Complete rewrite | LED control fully redesigned |
| `daemon/soundtrigger.py` | +25 lines | Added audio completion detection |
| Documentation | New files | Complete reference guides |

**Important**: Audio playback logic is completely untouched. Only LED control changed.

---

## Troubleshooting

### "GPIO not available - simulation mode"
- **Normal** if running on non-Raspberry Pi hardware
- System still works for testing

### LEDs not flashing when button pressed
1. Check both daemons are running
2. Verify GPIO wiring (continuity test)
3. Check `/tmp/sound_led_events` exists: `ls -la /tmp/sound_led_events`

### Pulsing looks jerky
Edit `daemon/led_daemon.py`, reduce sleep time in `_idle_pulsing_loop()` from 0.05 to 0.02

---

## Documentation Map

```
LED_QUICK_START.txt
├─ Hardware setup
├─ Testing procedures
├─ Common questions
└─ Customization options

LED_IMPLEMENTATION_SUMMARY.md
├─ Complete overview
├─ Architecture diagrams
├─ Event flow
├─ Configuration details
└─ Testing instructions

docs/LED_CONTROL.md
├─ Technical documentation
├─ System architecture
├─ Event protocol
├─ Troubleshooting
└─ Integration guide

docs/GPIO_PINOUT.md
├─ GPIO reference
├─ Wiring diagrams
├─ Pin mapping
└─ Alternative GPIO options

IMPLEMENTATION_COMPLETE.md
├─ Implementation status
├─ Verification checklist
├─ Files modified
└─ Next steps

CHANGES_SUMMARY.txt
├─ Visual overview
├─ File changes
├─ Testing procedures
└─ Support information
```

---

## Quick Command Reference

```bash
# Start LED daemon
python3 daemon/led_daemon.py

# Start audio daemon
python3 daemon/soundtrigger.py

# Test: send button press signal
echo "1" > /tmp/sound_led_events

# Test: send stop signal
echo "0" > /tmp/sound_led_events

# Check FIFO exists
ls -la /tmp/sound_led_events

# View LED daemon logs
journalctl -u sound-led-daemon -f

# Set custom GPIO pin
export LED_GPIO=12
python3 daemon/led_daemon.py
```

---

## Next Steps

1. ✅ Read [`LED_QUICK_START.txt`](LED_QUICK_START.txt)
2. ✅ Test in simulation mode (no hardware needed)
3. ✅ Wire GPIO 18 to LED circuit
4. ✅ Test with hardware
5. ✅ Adjust timings if needed
6. ✅ (Optional) Set up systemd service

---

## Getting Help

**For quick answers**: Check [`LED_QUICK_START.txt`](LED_QUICK_START.txt)

**For technical details**: Read [`docs/LED_CONTROL.md`](docs/LED_CONTROL.md)

**For wiring questions**: See [`docs/GPIO_PINOUT.md`](docs/GPIO_PINOUT.md)

**For implementation info**: Read [`LED_IMPLEMENTATION_SUMMARY.md`](LED_IMPLEMENTATION_SUMMARY.md)

---

## Summary

✨ The LED control system has been redesigned for simplicity, reliability, and ease of use.

🔌 **Hardware**: Connect GPIO 18 and GND to your LED circuit (2 wires total)

🎯 **Behavior**: 
- Idle: Gentle 5-second pulsing
- Button pressed: Rapid flashing
- Audio finishes: Back to pulsing

🚀 **Ready to test**: Follow [`LED_QUICK_START.txt`](LED_QUICK_START.txt)

---

**Status**: ✅ Implementation complete and ready for deployment
