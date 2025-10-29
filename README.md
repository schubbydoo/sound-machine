
### ALSA device selection


## Quick Tests


## Pico Firmware (MicroPython)

# Sound Machine (Pico + Pi Zero 2W)

Low-latency wired sound machine using a Raspberry Pi Pico (RP2040) for 16 buttons (with 4 LED buttons) and a Raspberry Pi Zero 2W for audio playback and web UI.

- **Transport**: USB CDC (Pico → Pi over USB)
- **Audio**: USB DAC on the Pi (WAV files for minimal start latency)
- **Latency target**: <30–50 ms button→sound using warmed ALSA and WAV
- **Sound Interruption**: New button presses immediately stop current playback
- **LED Feedback**: Glass skull LED lights respond to button presses and audio playback
- **Web Interface**: Full-featured web UI with navigation, WiFi, and Bluetooth management

## Hardware Summary
- **Buttons → Pico**: active-low to GND
  - Buttons 1–12 → GP2..GP13
  - Buttons 13–16 → GP18..GP21
  - GND daisy-chained across all switches
- **LED Control**: GPIO 18 (BCM) on Raspberry Pi Zero (physical pin 12)
  - Provides PWM signal to control LED switch circuit
  - Single wire + ground connection
- **Pi Zero 2W**: 4-port USB hat (Pico + USB DAC connected)
- **Pico firmware protocol**:
  - Sends: `P,<id>\n` on press
  - Receives: `L,<id>,0|1\n` for LED override

## Directory Layout
```
sound-machine/
├─ README.md
├─ daemon/
│  ├─ soundtrigger.py          # Main daemon (Pico->play WAV->LED signal)
│  ├─ led_daemon.py            # LED control daemon (PWM pulsing + flashing)
│  ├─ peek_pico.py             # Simple test for presses + LED override
│  ├─ test_leds.py             # LED blinking test script
│  └─ test_events.py           # Button event simulation script
├─ config/
│  └─ mappings.json            # Profiles + button->file mapping
├─ systemd/
│  ├─ soundtrigger.service     # Systemd unit to autostart audio daemon
│  └─ sound-led-daemon.service # Systemd unit to autostart LED daemon
├─ Sounds/
│  ├─ effects/                 # WAV files for "effects" profile
│  └─ trivia/                  # WAV files for "trivia" profile (optional)
├─ web_interface/              # Optional web UI (backend/frontend)
├─ docs/
│  ├─ wiring.md                # Pin map, LED wiring, photos
│  ├─ troubleshooting.md       # Common issues
│  ├─ LED_CONTROL.md           # Detailed LED system documentation
│  ├─ GPIO_PINOUT.md           # GPIO reference and wiring guide
│  ├─ LED_QUICK_START.txt      # LED quick start guide
│  ├─ LED_IMPLEMENTATION_SUMMARY.md # Implementation details
│  ├─ CHANGES_SUMMARY.txt      # Summary of changes
│  └─ IMPLEMENTATION_COMPLETE.md # Implementation status
└─ pico_firmware/
   ├─ boot.py
   ├─ main.py
   ├─ main_robust.py
   └─ main_no_leds.py
```

## Quick Start (Pi Zero 2W)
1. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv python3-serial alsa-utils
   ```
2. (Optional) Create a virtualenv and install `pyserial`:
   ```bash
   cd /home/soundconsole/sound-machine
   python3 -m venv .venv
   . .venv/bin/activate
   pip install pyserial
   ```
3. Put your WAV files into `Sounds/effects` (and/or `Sounds/trivia`). Prefer 16‑bit PCM WAV, 44.1k/48k.
4. Edit `config/mappings.json` to map button IDs (1..16) to WAV filenames.
5. Plug the Pico via USB (should appear as `/dev/ttyACM0`).
6. Try the serial peek tool:
   ```bash
   python3 daemon/peek_pico.py --port /dev/ttyACM0
   ```
7. Run the daemons manually for a quick test:
   ```bash
   # Terminal 1: LED daemon
   python3 daemon/led_daemon.py
   
   # Terminal 2: Audio daemon
   python3 daemon/soundtrigger.py
   ```
8. Install as systemd services (recommended for auto-start on boot):
   ```bash
   sudo ./SETUP_SYSTEMD.sh
   ```

## Configuration (`config/mappings.json`)
- **activeProfile**: the profile name to use.
- **device.serial**: serial device path for Pico (e.g., `/dev/ttyACM0`).
- **device.aplayDevice**: ALSA device for `aplay` (e.g., `plughw:0,0` for USB DAC).
- **profiles[<name>].baseDir**: absolute path to profile sound directory.
- **profiles[<name>].buttons**: map of button ID → WAV filename (relative to `baseDir`).

Example template:
```json
{
  "activeProfile": "effects",
  "device": {
    "serial": "/dev/ttyACM0",
    "aplayDevice": "plughw:0,0"
  },
  "profiles": {
    "effects": {
      "baseDir": "/home/soundconsole/sound-machine/Sounds/effects",
      "buttons": {
        "1": "sample1.wav",
        "2": "sample2.wav",
        "3": "sample3.wav",
        "4": "sample4.wav",
        "5": "",
        "6": "",
        "7": "",
        "8": "",
        "9": "",
        "10": "",
        "11": "",
        "12": "",
        "13": "",
        "14": "",
        "15": "",
        "16": ""
      }
    },
    "trivia": {
      "baseDir": "/home/soundconsole/sound-machine/Sounds/trivia",
      "buttons": {}
    }
  }
}
```

## Web Interface
The sound machine includes a full-featured web interface accessible at `http://localhost:8080` (or your Pi's IP address).

### Features
- **Sound Management**: Upload, delete, and assign WAV files to buttons
- **Real-time Testing**: Play sounds directly from the web interface
- **WiFi Configuration**: Connect to wireless networks with auto-connect settings
- **Bluetooth Setup**: Connect and manage Bluetooth audio devices
- **Navigation**: Clean, responsive interface with Bulma CSS framework

### Starting the Web Server
```bash
cd /home/soundconsole/sound-machine
source .venv/bin/activate
pip install flask gunicorn
gunicorn -w 2 -b 0.0.0.0:8080 web_interface.backend.wsgi:application
```

## Systemd Services
Two systemd units manage auto-start on boot:

- `systemd/sound-led-daemon.service`: Starts LED control daemon (auto-restarts on failure)
- `systemd/soundtrigger.service`: Starts audio daemon (auto-restarts on failure)

### Setup
```bash
# Automated setup (recommended)
sudo ./SETUP_SYSTEMD.sh

# Or manual setup
sudo cp systemd/sound-led-daemon.service /etc/systemd/system/
sudo cp systemd/soundtrigger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sound-led-daemon.service
sudo systemctl enable --now soundtrigger.service
```

### Service Management
```bash
# Check status
systemctl status sound-led-daemon.service
systemctl status soundtrigger.service

# View logs
journalctl -u sound-led-daemon.service -f
journalctl -u soundtrigger.service -f

# Restart
sudo systemctl restart sound-led-daemon.service
sudo systemctl restart soundtrigger.service
```

## LED Control System

### Overview
The system includes a sophisticated **autonomous LED daemon** that provides real-time visual feedback:

- **Idle State**: Smooth PWM pulsing (5-second breathing cycle) when no buttons pressed
- **Button Press**: Rapid LED flashing (100ms on/off) when audio is playing
- **Button Interrupt**: Flash sequence restarts if new button pressed before audio finishes
- **Audio Complete**: LEDs automatically return to idle pulsing when audio stops

### Hardware
- **GPIO Pin**: 18 (BCM numbering) = Pin 12 on GPIO header
- **Connection**: Single wire to LED circuit + ground
- **PWM Support**: Enables smooth brightness transitions

### For Detailed LED Documentation
See the comprehensive LED documentation:
- **Quick Start**: `docs/LED_QUICK_START.txt`
- **Full Details**: `docs/LED_CONTROL.md`
- **GPIO Reference**: `docs/GPIO_PINOUT.md`
- **Implementation Details**: `docs/LED_IMPLEMENTATION_SUMMARY.md`

### Running the LED Daemon
```bash
# Manual execution
python3 daemon/led_daemon.py

# Or via systemd (recommended)
sudo systemctl start sound-led-daemon.service
sudo systemctl status sound-led-daemon.service
```

## Performance Features
- **Sound Interruption**: New button presses immediately stop current playback for responsive switching
- **Optimized Debouncing**: 200ms debounce window for reliable operation with cheap arcade buttons
- **LED Feedback**: Real-time visual feedback with PWM pulsing and flashing
- **Rapid Button Handling**: System handles rapid button mashing without getting confused
- **Autonomous Operation**: LED daemon runs independently, works even if audio daemon crashes
- **Kid-Friendly**: Designed to handle enthusiastic button pressing without lockups
- **Simplified Audio**: Direct ALSA access without audio server conflicts for maximum reliability
- **Automatic Volume**: Volume automatically set to 100% on startup

## Notes on Latency
- Use WAV (PCM) files and `aplay` for minimal startup overhead.
- Keep files small and pre-warm the USB DAC by playing a short silent clip on boot if needed.
- Consider a dedicated USB DAC and set `device.aplayDevice` accordingly.
- Optimized daemon with sound interruption achieves <30-50ms button→sound latency.

## Troubleshooting
- Check serial device presence: `ls /dev/ttyACM*`.
- Test audio output: `aplay -D plughw:0,0 /path/to/test.wav`.
- View logs: `journalctl -u soundtrigger.service -e`.
- **Communication Issues**: If buttons stop working or Pico drops into REPL mode, use `main_robust.py` firmware instead of `main.py`.
- **Pico Not Responding**: Test with `python3 daemon/peek_pico.py --port /dev/ttyACM0` - should show button states.
- **Audio Format Errors**: The daemon uses simplified aplay commands - files should already be in correct format (16-bit PCM WAV).
- **Cheap Arcade Buttons**: The system uses 200ms debouncing to handle multiple presses from cheap arcade buttons reliably.
- **Serial Stability**: Simplified serial communication with reliable settings for stable operation.
- **Pico Reset**: If the Pico stops responding, send reset commands: `python3 -c "import serial; ser=serial.Serial('/dev/ttyACM0', 115200); ser.write(b'\x03\x04'); ser.close()"`
- **Service Not Working After Code Changes**: After updating the daemon code, restart the service: `sudo systemctl restart soundtrigger.service`
- **Service Status Check**: Check if the service is running: `sudo systemctl status soundtrigger.service`
- **No Sound Output**: Volume is automatically set to 100% on startup. If issues persist, check: `amixer -c 0`
- **Audio Conflicts**: The system uses direct ALSA access for maximum reliability. No audio servers (PipeWire/PulseAudio) are needed.
- See `docs/troubleshooting.md` for more.

## Pico Firmware (MicroPython)
Firmware lives in `pico_firmware/`:
- `boot.py`: minimal boot configuration.
- `main.py`: implements button scanning, press reporting (`P,<id>`), LED overrides (`L,<id>,0|1`), and background random twinkle for LED buttons 1,7,9,15.
- `main_robust.py`: **RECOMMENDED** - Robust version that handles interrupts gracefully and prevents communication fragility issues.
- `main_no_leds.py`: Simplified version without LED management for Picos without LEDs.

### Firmware Versions
- **`main_robust.py`** (Recommended): Handles KeyboardInterrupt and serial communication interruptions gracefully. This version prevents the Pico from dropping into REPL mode when interrupted by the daemon.
- **`main.py`**: Original version with LED management. Use only if you have LEDs and need the original functionality.
- **`main_no_leds.py`**: Simplified version without LED management for Picos without LED hardware.

### Flashing steps
1. Download MicroPython UF2 for Pico (RP2040) from `https://micropython.org/download/RPI_PICO/`.
2. Hold BOOTSEL on the Pico and plug into the Pi; a drive `RPI-RP2` appears.
3. Copy the UF2 onto `RPI-RP2`. It reboots into MicroPython.
4. Mount the MicroPython filesystem (appears as a serial REPL on `/dev/ttyACM0`).
5. Copy `pico_firmware/boot.py` and `pico_firmware/main_robust.py` onto the Pico as `/boot.py` and `/main.py`:
   ```bash
   # Option A: using mpremote (recommended)
   pip install mpremote
   mpremote connect /dev/ttyACM0 fs cp pico_firmware/boot.py :boot.py
   mpremote connect /dev/ttyACM0 fs cp pico_firmware/main_robust.py :main.py
   mpremote connect /dev/ttyACM0 reset

   # Option B: using rshell
   pip install rshell
   rshell -p /dev/ttyACM0 cp pico_firmware/boot.py /pyboard/boot.py
   rshell -p /dev/ttyACM0 cp pico_firmware/main_robust.py /pyboard/main.py
   ```
6. After reset, the Pico should print presses and accept LED overrides.

### Wiring check
- Buttons are active-low with pull-ups enabled on the Pico.
- LED pins: 1→GP14, 7→GP15, 9→GP16, 15→GP17. Anodes via ~330 Ω to GPIO, cathodes to GND.
- If your LED mapping differs, adjust `LED_BUTTON_TO_PIN` in `main.py` accordingly.


## Quick Tests
- LED override test:
  ```bash
  python3 daemon/peek_pico.py --port /dev/ttyACM0 --led 1:on
  sleep 0.5
  python3 daemon/peek_pico.py --port /dev/ttyACM0 --led 1:off
  ```
- Generate a test tone and map to button 1:
  ```bash
  python3 - << 'PY'
import wave, struct, math
fr=44100; dur=0.25; freq=880
n=int(fr*dur)
with wave.open('Sounds/effects/sample1.wav','w') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr)
    for i in range(n):
        val=int(32767*0.7*math.sin(2*math.pi*freq*i/fr))
        w.writeframesraw(struct.pack('<h', val))
PY
  sed -i 's/"1": "[^"]*"/"1": "sample1.wav"/' config/mappings.json
  ```
- Audio output test:
  ```bash
  aplay Sounds/effects/sample1.wav
  ```
- Daemon smoke test (press button 1 while it runs):
  ```bash
  python3 daemon/soundtrigger.py
  ```

### ALSA device selection
- List devices: `aplay -l`
- Try `plughw:<card>,<device>` for the USB DAC, e.g., `plughw:0,0`.
- Set `device.aplayDevice` in `config/mappings.json` accordingly.
- If HDMI is default, force the USB DAC by using `-D plughw:0,0`.
