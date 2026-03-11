# Sound Machine (Pico + Pi Zero 2W)

Low-latency wired sound machine using a Raspberry Pi Pico (RP2040) for 16 buttons (with 4 LED buttons) and a Raspberry Pi Zero 2W for audio playback, web UI, and profile management via a touchscreen kiosk display.

- **Transport**: USB CDC (Pico → Pi over USB)
- **Audio**: USB DAC on the Pi (WAV files for minimal start latency)
- **Latency target**: <30–50 ms button→sound using warmed ALSA and WAV
- **Sound Interruption**: New button presses immediately stop current playback
- **LED Feedback**: Glass skull LED lights respond to button presses and audio playback
- **Touchscreen Kiosk**: 800×480 touch display for profile selection, hint/reveal, and library management
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
- **Touchscreen**: QDtech MPI5001 800×480 display (evdev driver)
  - Replaces the previous 4-position rotary knob for profile switching
  - Runs the kiosk UI on `:0 vt1` via `surf` (WebKitGTK)
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
│  ├─ peek_pico.py             # Simple test for presses + LED override
│  └─ test_leds.py             # LED blinking test script
├─ kiosk/
│  ├─ kiosk_server.py          # Flask server for touchscreen UI (port 8081)
│  ├─ start-kiosk.sh           # X session startup (surf browser, openbox)
│  ├─ templates/
│  │  ├─ kiosk.html            # Main play surface (track select, hint/reveal, stop)
│  │  └─ library.html          # Library management (playlist curation, cloud download)
│  ├─ systemd/
│  │  └─ kiosk-server.service  # Autostart kiosk server
│  └─ xorg/
│     └─ 99-touch.conf         # QDtech touchscreen evdev config
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
The system uses a **SQLite database** for all configuration.

- **Profiles**: Create multiple sound profiles (e.g., "Horror", "Trivia", "Sci-Fi").
- **Playlist**: Profiles are added to a playlist and selected from the touchscreen kiosk.
- **Assignments**: Map any uploaded WAV file to any of the 16 buttons for a specific profile.

All configuration is done via the **Web Interface** (port 8080). The **Kiosk** (port 8081) handles in-game profile selection and hint/reveal.

## Web Interface
The sound machine includes a full-featured web interface accessible at `http://<pi-ip>:8080`.

### Features
- **Profile Management**: Create, Rename, Delete profiles.
- **Sound Management**:
    - Bulk upload WAV files (auto-assigns to buttons if requested).
    - **Overwrite Support**: Uploading a file with the same name replaces the existing file.
    - **File Management**: Selectively delete multiple audio files to free up space.
- **Metadata Editor**: Add Descriptions, Categories, and Hints to sounds for gameplay.
- **Answer Key / Worksheet**: One-click printable answer key and worksheet for the current profile.
- **Print Tracks Label**: Print a label listing track assignments for the physical device.
- **Real-time Testing**: Play sounds directly from the web dashboard.
- **Connectivity**: Manage Wi-Fi and Bluetooth connections directly from the UI.

## Kiosk Touchscreen
The kiosk runs on the local display (`:0 vt1`) using `surf` (WebKitGTK) and is served by a sidecar Flask server on port 8081. It is a **read-only play surface** — all content management is done via the web UI.

### Features
- **Track Selector**: Tap to pick the active profile from the playlist.
- **Hint / Reveal**: Show a hint or reveal the answer for the last-pressed button.
- **Stop**: Stop audio playback.
- **Library**: Browse local and cloud track packs, manage the playlist.

### Surf Browser — Patched Build
The stock `surf` package does not suppress the WebKitGTK `context-menu` signal, which causes a navigation menu (Back/Forward/Stop/Reload) to appear on long-press. The binary at `/usr/local/bin/surf` is a locally compiled patched version that suppresses this signal entirely.

**Source location on Pi**: `/tmp/surf-2.1/` (patched `surf.c`).

To rebuild after a `sudo apt upgrade` replaces `/usr/local/bin/surf`:
```bash
cd /tmp/surf-2.1
make && sudo make install
pkill -f "surf -b"   # kiosk auto-restarts via getty → bash_profile → startx
```

### Kiosk Startup Chain
```
getty@tty1 → autologin → ~/.bash_profile → startx start-kiosk.sh
  └─ xset (no blanking/screensaver)
  └─ unclutter (hide cursor)
  └─ openbox (window manager)
  └─ GTK_LONG_PRESS_TIME=30000 surf -b -d http://localhost:8081
```

To reload the kiosk after template changes (no reboot needed):
```bash
pkill -f "surf -b"   # surf exits → xinit exits → getty respawns → kiosk restarts
```

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
- `webui.service`: Serves the Web Interface on port 8080 (gunicorn)
- `kiosk-server.service`: Serves the Kiosk UI on port 8081 (Flask)

The kiosk display (surf browser) is started by `getty@tty1` autologin, not systemd directly.

### Service Management
```bash
# Check status
systemctl status sound-led-daemon.service
systemctl status soundtrigger.service
systemctl status kiosk-server.service
systemctl status webui.service

# View logs
journalctl -u soundtrigger.service -f
journalctl -u kiosk-server.service -f
```

## LED Control System
The system includes a sophisticated **autonomous LED daemon** that provides real-time visual feedback via GPIO 18.
- **Idle State**: Smooth PWM pulsing.
- **Button Press**: Rapid LED flashing when audio is playing.

## Troubleshooting
- **No Sound**: Ensure `aplay -l` shows your device. Check volume with `amixer -c 0`.
- **Database Locked**: If the web UI hangs, restart the service: `sudo systemctl restart webui.service`.
- **Kiosk blank / not loading**: Check `systemctl status kiosk-server.service`. Restart with `pkill -f "surf -b"`.
- **Context menu appearing on long-press**: The patched surf build at `/usr/local/bin/surf` may have been overwritten by `apt upgrade`. Rebuild from `/tmp/surf-2.1/` — see **Surf Browser — Patched Build** above.
