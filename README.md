# Sound Machine (Pico + Pi Zero 2W)

Low-latency wired sound machine using a Raspberry Pi Pico (RP2040) for 16 buttons (with 4 LED buttons) and a Raspberry Pi Zero 2W for audio playback, web UI, and profile management via a physical 4-position rotary switch.

- **Transport**: USB CDC (Pico → Pi over USB)
- **Audio**: USB DAC on the Pi (WAV files for minimal start latency)
- **Latency target**: <30–50 ms button→sound using warmed ALSA and WAV
- **Sound Interruption**: New button presses immediately stop current playback
- **LED Feedback**: Glass skull LED lights respond to button presses and audio playback
- **Channel Knob**: 4-position rotary switch for instant profile switching
- **Web Interface**: Full-featured web UI for profile management, bulk uploads (with overwrite support), selective file deletion, metadata editing, and Answer Key/Label generation.
- **Styling**: Bulma CSS framework for a responsive and modern UI.

## Hardware Summary
- **Buttons → Pico**: active-low to GND
  - Buttons 1–12 → GP2..GP13
  - Buttons 13–16 → GP18..GP21
  - GND daisy-chained across all switches
- **LED Control**: GPIO 18 (BCM) on Raspberry Pi Zero (physical pin 12)
  - Provides PWM signal to control LED switch circuit
  - Single wire + ground connection
- **Channel Knob**: 4-position rotary switch connected to Pi Zero 2W GPIO
  - Channel 1 (Track 1): GPIO 22 (Yellow)
  - Channel 2 (Track 2): GPIO 23 (Orange)
  - Channel 3 (Track 3): GPIO 24 (Red)
  - Channel 4 (Track 4): GPIO 25 (Brown)
  - Common: GND (Black)
- **Pi Zero 2W**: 4-port USB hat (Pico + USB DAC connected)
- **Pico firmware protocol**:
  - Sends: `P,<id>\n` on press
  - Receives: `L,<id>,0|1\n` for LED override

## Directory Layout
```
sound-machine/
├─ README.md
├─ daemon/
│  ├─ soundtrigger.py          # Main daemon (Pico->DB query->play WAV->LED signal)
│  ├─ led_daemon.py            # LED control daemon (PWM pulsing + flashing)
│  ├─ channel_monitor.py       # Watches rotary switch (GPIO 22-25) and updates DB
│  ├─ peek_pico.py             # Simple test for presses + LED override
│  └─ test_leds.py             # LED blinking test script
├─ config/
│  ├─ wifi.json                # WiFi settings
│  └─ bt.json                  # Bluetooth settings
├─ data/
│  └─ sound_machine.db         # SQLite database (Profiles, Mappings, Metadata)
├─ systemd/
│  ├─ soundtrigger.service           # Autostart audio daemon
│  ├─ sound-led-daemon.service       # Autostart LED daemon
│  └─ sound-channel-monitor.service  # Autostart channel monitor
├─ Sounds/
│  ├─ uploads/                 # Storage for uploaded files
│  └─ effects/                 # Legacy folder
├─ web_interface/              # Web UI (Flask)
├─ docs/
│  ├─ requirements.md          # Project requirements
│  ├─ wiring.md                # Pin map, LED wiring, photos
│  └─ ...
└─ pico_firmware/
   └─ ...
```

## Quick Start (Pi Zero 2W)
1. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv python3-serial alsa-utils sqlite3
   ```
2. (Optional) Create a virtualenv and install python libs:
   ```bash
   cd /home/soundconsole/sound-machine
   python3 -m venv .venv
   . .venv/bin/activate
   pip install pyserial flask gunicorn
   ```
3. Initialize the database (if fresh install):
   ```bash
   python3 db/init_db.py
   ```
4. Install systemd services:
   ```bash
   sudo ./SETUP_SYSTEMD.sh
   ```

## Configuration & Profiles
The system now uses a **SQLite database** instead of a JSON file for configuration.

- **Profiles**: Create multiple sound profiles (e.g., "Horror", "Trivia", "Sci-Fi").
- **Tracks (Channels)**: Assign any profile to one of the 4 hardware channels (Rotary Knob positions).
- **Assignments**: Map any uploaded WAV file to any of the 16 buttons for a specific profile.

All configuration is done via the **Web Interface**.

## Web Interface
The sound machine includes a full-featured web interface accessible at `http://localhost:8080` (or your Pi's IP address).

### Features
- **Profile Management**: Create, Rename, Delete profiles.
- **Track Assignment**: Map profiles to the physical rotary knob positions (Tracks 1-4).
- **Sound Management**: 
    - Bulk upload WAV files (auto-assigns to buttons if requested).
    - **Overwrite Support**: Uploading a file with the same name replaces the existing file.
    - **File Management**: Selectively delete multiple audio files to free up space.
- **Metadata Editor**: Add Descriptions, Categories, and Hints to sounds for gameplay.
- **Answer Key**: One-click generation of a printable answer key. Includes customizable columns (Track, Button #, Description, Category, Hint, Filename) and persistent settings.
- **Print Tracks Label**: New feature to print a small, formatted label for the physical device, listing the current "Track" (Channel) assignments.
- **Real-time Testing**: Play sounds directly from the web dashboard.
- **Connectivity**: Manage Wi-Fi and Bluetooth connections directly from the UI.

### Starting the Web Server manually
```bash
cd /home/soundconsole/sound-machine
source .venv/bin/activate
gunicorn -w 2 -b 0.0.0.0:8080 web_interface.backend.wsgi:application
```

## Systemd Services
Four systemd units manage auto-start on boot:

- `sound-led-daemon.service`: Starts LED control daemon (auto-restarts on failure)
- `soundtrigger.service`: Starts audio daemon (auto-restarts on failure)
- `sound-channel-monitor.service`: Monitors the rotary knob for profile switching
- `webui.service`: Serves the Web Interface (gunicorn)

### Service Management
```bash
# Check status
systemctl status sound-led-daemon.service
systemctl status soundtrigger.service
systemctl status sound-channel-monitor.service

# View logs
journalctl -u soundtrigger.service -f
journalctl -u sound-channel-monitor.service -f
```

## LED Control System
The system includes a sophisticated **autonomous LED daemon** that provides real-time visual feedback via GPIO 18.
- **Idle State**: Smooth PWM pulsing.
- **Button Press**: Rapid LED flashing when audio is playing.

## Troubleshooting
- **No Sound**: Ensure `aplay -l` shows your device. Check volume with `amixer -c 0`.
- **Knob Not Working**: Check `journalctl -u sound-channel-monitor.service`. Ensure GPIOs 22-25 are wired correctly to GND via the switch.
- **Database Locked**: If the web UI hangs, restart the service: `sudo systemctl restart webui.service`.
