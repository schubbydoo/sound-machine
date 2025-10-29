# LED Implementation Summary

## What Changed

The LED control system has been completely redesigned to be **simple, autonomous, and modular**. Instead of trying to sync LEDs to audio in complex ways, the system now uses a clean state machine that responds to button presses and audio completion events.

## Files Modified

### 1. `daemon/led_daemon.py` - Complete Rewrite
**What was removed:**
- Complex multi-color LED mapping (red, yellow, blue, etc.)
- Random blinking patterns
- Timeout-based shutdown (unreliable)
- Color pair combinations

**What was added:**
- **Single GPIO control** with PWM support
- **State machine** (IDLE vs FLASHING)
- **Idle pulsing**: Smooth 5-second breathing effect (20% to 100% brightness)
- **Flash on button press**: Rapid 100ms on/off flashing
- **Clean event handling**: Button ID = start/restart flash, button ID 0 = stop and return to idle

### 2. `daemon/soundtrigger.py` - Minimal Additions
**What was added:**
- `send_led_stop_signal()` - New function to signal LED daemon when audio finishes
- `monitor_audio_playback()` - New thread that watches for audio completion
  - Detects when `aplay` process exits
  - Sends button ID 0 (stop signal) to LED daemon
  - Enables LEDs to return to idle pulsing after audio stops

**What wasn't changed:**
- Audio playback logic - still works exactly as before
- Button press handling - no changes
- Serial communication - untouched

### 3. Documentation Added
- `docs/LED_CONTROL.md` - Complete LED system documentation
- `docs/GPIO_PINOUT.md` - GPIO reference and wiring guide
- `LED_IMPLEMENTATION_SUMMARY.md` - This file

## Hardware Setup

### GPIO Pin Selection

**Default: GPIO 18 (Pin 12 on header)**

If GPIO 18 conflicts with other hardware:
```bash
export LED_GPIO=12   # Use GPIO 12 instead
export LED_GPIO=13   # Use GPIO 13 instead
export LED_GPIO=19   # Use GPIO 19 instead
export LED_GPIO=26   # Use GPIO 26 instead
```

### Physical Wiring

1. **Locate GPIO 18 (Pin 12) and Ground (Pin 9) on Raspberry Pi header**
2. **Connect to LED circuit:**
   - GPIO 18 (Pin 12) → LED switch signal input
   - GND (Pin 9) → Common ground with LED circuit
3. **Verify connections** with continuity tester if available

### Diagram
```
Raspberry Pi Zero (GPIO Header)
┌────────────────────┐
│  Pin 1  │ Pin 2   │  +3.3V, +5V
│  Pin 3  │ Pin 4   │
│  ...    │ ...     │
│  Pin 9  │ Pin 10  │  ← GND is Pin 9
│  ...    │ ...     │
│  Pin 11 │ Pin 12  │  ← GPIO 18 is Pin 12 (your signal)
│  ...    │ ...     │
└────────────────────┘

Connect:
  Pin 12 (GPIO 18) ──→ LED Switch Input
  Pin 9 (GND)      ──→ LED Circuit Ground
```

## Operating Behavior

### Idle State (No Button Press)
```
LED Brightness Timeline:
100% ╱╲    ╱╲
     │ ╲  ╱ ╲
 50% │  ╲╱   ╲╱╲
     │           ╲
  0% ╲___________╱
     └─────────────────→ Time (5 seconds per cycle)
```
- Smooth pulsing, repeats continuously
- Signals that system is ready for input
- Low-key, not distracting

### Button Pressed State
```
LED Brightness Timeline:
100% ┬─┬─┬─┬─
     │ │ │ │ │
  0% ┴─┴─┴─┴─┴─ ...
     └─ 100ms ─┘ (100ms on, 100ms off, repeats)
```
- Rapid on/off flashing
- Clear feedback that button was pressed
- Continues until audio finishes

### Interrupt Scenario
```
Timeline:
Button 1 pressed    → Flash starts
  (audio playing)   → Flash continues
Button 2 pressed    → Flash RESTARTS from beginning
  (audio playing)   → New flash sequence
Audio finishes      → Flash stops, return to pulsing
```
- Restart is clean and immediate
- Provides visual feedback of new action

## Event Flow Diagram

```
┌──────────────┐
│  Button      │
│  Pressed     │
└──────┬───────┘
       │
       ↓
┌──────────────────────┐
│ Audio Daemon reads   │
│ button from Pico     │
└──────┬───────────────┘
       │
       ├─→ Play audio file via aplay
       │
       └─→ Send button ID to LED daemon
           via /tmp/sound_led_events
           
           ↓
┌──────────────────────┐
│ LED Daemon receives  │
│ button ID            │
└──────┬───────────────┘
       │
       ↓
    State = FLASHING
    Start 100ms on/off
    
    [Audio is playing and LED is flashing]
    
    (Meanwhile, audio daemon monitors aplay process)
    
    ↓
    aplay process exits
    (audio finished)
    
    ↓
    Audio daemon sends
    button ID = 0 (stop signal)
    
    ↓
┌──────────────────────┐
│ LED Daemon receives  │
│ stop signal (0)      │
└──────┬───────────────┘
       │
       ↓
    State = IDLE
    Return to pulsing
```

## Testing

### Quick Test (Simulation Mode)

If GPIO not available, the LED daemon runs in simulation mode:

```bash
# Start LED daemon (will print debug output)
cd /home/soundconsole/sound-machine
python3 daemon/led_daemon.py

# In another terminal, simulate events
echo "1" > /tmp/sound_led_events  # Button 1 pressed → should print "FLASHING"
sleep 2
echo "2" > /tmp/sound_led_events  # Button 2 pressed → should print "FLASHING" again
sleep 3
echo "0" > /tmp/sound_led_events  # Stop → should print "IDLE"
```

### Full System Test

Once wired:

1. **Start the daemons:**
   ```bash
   # Terminal 1: LED daemon
   python3 daemon/led_daemon.py
   
   # Terminal 2: Audio daemon
   python3 daemon/soundtrigger.py
   ```

2. **Press buttons on the Pico**
   - LEDs should flash immediately when button pressed
   - LEDs should stop flashing when audio finishes
   - Pressing another button should restart the flash

3. **Check LED behavior:**
   - Idle: Smooth pulsing, not too bright or dim
   - Button press: Obvious rapid flashing
   - Audio finish: Smooth transition back to pulsing

## Customization Options

### Adjust Pulsing Speed
Edit `daemon/led_daemon.py`:
```python
PULSE_CYCLE_SECONDS = 5.0  # Change from 5 to 3 for faster pulsing
```

### Adjust Pulsing Brightness Range
```python
IDLE_MIN_PWM = 20   # Minimum brightness (0-100)
IDLE_MAX_PWM = 100  # Maximum brightness (0-100)
# e.g., to pulse between 40-80%: MIN=40, MAX=80
```

### Adjust Flashing Speed
```python
FLASH_ON_MS = 100   # On duration (milliseconds)
FLASH_OFF_MS = 100  # Off duration (milliseconds)
# e.g., for faster flash: ON=50, OFF=50
```

## Troubleshooting

### "LED: GPIO not available - simulation mode"
- This is normal if not running on a Raspberry Pi
- The daemon will still work and print debug messages

### LEDs Not Flashing When Button Pressed
1. Check daemons are both running
2. Verify GPIO pin wiring
3. Check `/tmp/sound_led_events` exists:
   ```bash
   ls -la /tmp/sound_led_events
   ```
4. Check for GPIO permission issues:
   ```bash
   sudo usermod -aG gpio soundconsole
   ```

### Pulsing Looks Jerky
- Reduce `time.sleep()` in `_idle_pulsing_loop()` from 0.05 to 0.02
- This updates PWM more frequently for smoother transitions

### Flashing Timing Seems Off
- Check `FLASH_ON_MS` and `FLASH_OFF_MS` settings
- System CPU load affects timing slightly

## Integration with Systemd

If you're using systemd services, ensure proper start order:

```ini
# /etc/systemd/system/sound-led-daemon.service
[Unit]
Description=Sound Machine LED Control
After=network.target
Before=sound-trigger.service

[Service]
Type=simple
User=soundconsole
ExecStart=/usr/bin/python3 /home/soundconsole/sound-machine/daemon/led_daemon.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sound-led-daemon.service
sudo systemctl start sound-led-daemon.service
```

## What Happens If Audio Daemon Crashes?

- LED daemon continues running independently
- LEDs will remain in idle pulsing state
- When audio daemon restarts, LED control resumes normally
- No synchronization issues or stuck states

## Summary of Improvements

✅ **Simple**: Single GPIO pin instead of 5 individual colored LEDs  
✅ **Autonomous**: LED daemon is independent, can run standalone  
✅ **Reliable**: State machine instead of timeout-based logic  
✅ **Responsive**: Immediate feedback on button press  
✅ **Modular**: Clean signaling protocol between audio and LED  
✅ **Configurable**: Easy to adjust timings and GPIO pin  
✅ **Maintainable**: Less code, clearer intent  

## Next Steps

1. **Wire GPIO 18 to your LED switch circuit**
2. **Verify connections** with continuity tester
3. **Test in simulation mode** (no GPIO needed)
4. **Test with actual hardware** after wiring
5. **Adjust timings** if needed for your preference
6. **Integrate into systemd** for auto-startup (optional)

---

**Questions or issues?** Check `docs/LED_CONTROL.md` for detailed documentation.
