# LED Control System - Single GPIO Switch

## Overview

The LED control system has been simplified to use a **single GPIO pin** that controls an LED switch (for your glass skull with batteries). The system operates autonomously and independently from the audio daemon through simple event signaling via a named pipe.

## Hardware Setup

### GPIO Configuration

- **GPIO Pin**: `18` (configurable via `LED_GPIO` environment variable)
- **Connection**: GPIO 18 → LED Switch Control (single wire)
- **Type**: GPIO output with PWM support (for brightness control)

### Wiring

1. Connect GPIO 18 (BCM numbering) to your LED switch control circuit
2. The GPIO will provide PWM signals that the LED circuit responds to
3. Ground must be common between Raspberry Pi and LED switch circuit

### Changing the GPIO Pin

If GPIO 18 is already in use, set the environment variable:

```bash
export LED_GPIO=25  # Use GPIO 25 instead
```

## Operating Modes

### 1. Idle State (Waiting for Interaction)

**Behavior**: Smooth PWM pulsing - gradually increases from off to full brightness and back to off

- **Duration**: 5-second cycle (off → full brightness → off)
- **PWM Range**: 20% to 100% duty cycle
- **Purpose**: Visual feedback that the system is ready and waiting

### 2. Flashing State (Button Pressed)

**Behavior**: Rapid on/off flashing at 100ms intervals

- **On Time**: 100ms
- **Off Time**: 100ms
- **Trigger**: Any button press
- **Purpose**: Immediate visual feedback that a button was pressed

### 3. Interrupt Behavior

If a button is pressed while another is still playing:
- Previous flash sequence **restarts from the beginning**
- Provides clear visual feedback of the new action

## System Architecture

```
┌─────────────────────────────────────────────────┐
│ Raspberry Pi Zero                               │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ Audio Daemon (soundtrigger.py)          │  │
│  │ - Reads button presses from Pico        │  │
│  │ - Plays audio files via aplay           │  │
│  │ - Sends button ID on button press       │  │
│  │ - Sends stop signal (ID=0) when audio   │  │
│  │   playback finishes                     │  │
│  └──────────────┬──────────────────────────┘  │
│                 │ (named pipe)                 │
│                 │ /tmp/sound_led_events        │
│                 ↓                              │
│  ┌──────────────────────────────────────────┐  │
│  │ LED Daemon (led_daemon.py)               │  │
│  │ - Autonomous state machine               │  │
│  │ - IDLE: 5-sec pulse (PWM 20-100%)        │  │
│  │ - FLASHING: 100ms on/off                 │  │
│  │ - GPIO 18: PWM control signal            │  │
│  └──────────────┬──────────────────────────┘  │
│                 │ (GPIO PWM signal)            │
│                 │ (GPIO 18)                    │
│                 ↓                              │
│         ┌───────────────┐                      │
│         │ LED Switch    │                      │
│         │ Control       │                      │
│         └───────────────┘                      │
│                 │                              │
└─────────────────┼──────────────────────────────┘
                  │
                  ↓
         ┌────────────────┐
         │ Glass Skull    │
         │ with LEDs &    │
         │ Battery        │
         └────────────────┘
```

## Event Signaling Protocol

### Button Press Event

When a button is pressed:
1. Pico sends `P,<button_id>` to Audio Daemon
2. Audio Daemon plays audio file
3. Audio Daemon sends `<button_id>` to LED Daemon via named pipe
4. LED Daemon starts/restarts flashing

### Audio Finish Event

When audio playback completes:
1. Audio Daemon detects process exit
2. Audio Daemon sends `0` to LED Daemon via named pipe
3. LED Daemon stops flashing and returns to idle pulsing

## Configuration Files

### Audio Daemon (`soundtrigger.py`)

Key functions:
- `send_button_event_to_led_daemon(btn_id)` - Sends button ID to LED daemon
- `send_led_stop_signal()` - Sends stop signal (button ID 0)
- `monitor_audio_playback()` - Thread that detects when audio finishes

### LED Daemon (`led_daemon.py`)

Key components:
- `LEDState` enum - IDLE and FLASHING states
- `LEDController` class - Manages PWM and state transitions
- `_idle_pulsing_loop()` - Smooth breathing effect
- `_flashing_loop()` - Rapid on/off
- `button_pressed(button_id)` - Handles button events
- `stop_flashing()` - Stops flashing, returns to idle

## Testing

### Manual LED Test

```bash
# Start the LED daemon directly (for testing)
./daemon/led_daemon.py

# In another terminal, simulate button presses
echo "1" > /tmp/sound_led_events  # Start flashing
sleep 2
echo "2" > /tmp/sound_led_events  # Restart flash
sleep 3
echo "0" > /tmp/sound_led_events  # Stop, return to pulsing
```

### Environment Variables

```bash
# Set custom GPIO pin (default is 18)
export LED_GPIO=25

# Run LED daemon
./daemon/led_daemon.py
```

## Customization

### Adjusting Pulse Timing

Edit `/daemon/led_daemon.py`:

```python
PULSE_CYCLE_SECONDS = 5.0  # Change to adjust pulse speed
IDLE_MIN_PWM = 20  # Minimum brightness (0-100)
IDLE_MAX_PWM = 100  # Maximum brightness (0-100)
```

### Adjusting Flash Timing

Edit `/daemon/led_daemon.py`:

```python
FLASH_ON_MS = 100  # On duration in milliseconds
FLASH_OFF_MS = 100  # Off duration in milliseconds
```

## Troubleshooting

### LEDs Not Responding

1. Check GPIO pin is correct:
   ```bash
   gpio readall  # Display all GPIO pins
   ```

2. Verify FIFO is created:
   ```bash
   ls -la /tmp/sound_led_events
   ```

3. Check for errors in LED daemon logs:
   ```bash
   journalctl -u sound-led-daemon -f
   ```

### PWM Not Working

- Ensure GPIO pin supports PWM (most pins do on Raspi)
- Try a different pin: `export LED_GPIO=12` or `export LED_GPIO=13`

### Pulsing Looks Jerky

Adjust PWM update frequency in `_idle_pulsing_loop()`:
- Lower `time.sleep(0.05)` value = smoother pulsing (higher CPU)
- Higher value = choppier pulsing (lower CPU)

## System Integration

### Systemd Service

If using systemd to manage daemons, ensure LED daemon starts before audio daemon:

```ini
[Unit]
Description=Sound Machine LED Control
After=network.target
Before=sound-trigger.service

[Service]
Type=simple
User=soundconsole
ExecStart=/usr/local/bin/sound-led-daemon
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Summary

- **Single GPIO pin** (GPIO 18 by default) controls the LED switch
- **Autonomous operation** - LED daemon is independent from audio daemon
- **Simple signaling** - Button IDs and stop signal (0) via named pipe
- **Two modes** - Idle pulsing and button press flashing
- **Interrupt handling** - Restarts flash sequence on new button press
