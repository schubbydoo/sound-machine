
### ALSA device selection


## Quick Tests


## Pico Firmware (MicroPython)

# Sound Machine (Pico + Pi Zero 2W)

Low-latency wired sound machine using a Raspberry Pi Pico (RP2040) for 16 buttons (with 4 LED buttons) and a Raspberry Pi Zero 2W for audio playback and web UI.

- **Transport**: USB CDC (Pico → Pi over USB)
- **Audio**: USB DAC on the Pi (WAV files for minimal start latency)
- **Latency target**: <30–50 ms button→sound using warmed ALSA and WAV
- **Sound Interruption**: New button presses immediately stop current playback
- **Web Interface**: Full-featured web UI with navigation, WiFi, and Bluetooth management

## Hardware Summary
- **Buttons → Pico**: active-low to GND
  - Buttons 1–12 → GP2..GP13
  - Buttons 13–16 → GP18..GP21
  - GND daisy-chained across all switches
- **LED buttons**: 1, 7, 9, 15
  - LED GPIOs on Pico: GP14, GP15, GP16, GP17 (≈330 Ω series to LED anodes; cathodes to GND)
- **Pi Zero 2W**: 4-port USB hat (Pico + USB DAC connected)
- **Pico firmware protocol**:
  - Sends: `P,<id>\n` on press
  - Receives: `L,<id>,0|1\n` for LED override

## Directory Layout
```
sound-machine/
├─ README.md
├─ daemon/
│  ├─ soundtrigger.py          # Main daemon (Pico->play WAV->LED override)
│  └─ peek_pico.py             # Simple test for presses + LED override
├─ config/
│  └─ mappings.json            # Profiles + button->file mapping
├─ systemd/
│  └─ soundtrigger.service     # Systemd unit to autostart the daemon
├─ Sounds/
│  ├─ effects/                 # WAV files for "effects" profile
│  └─ trivia/                  # WAV files for "trivia" profile (optional)
├─ web_interface/              # Optional web UI (backend/frontend)
└─ docs/
   ├─ wiring.md                # Pin map, LED wiring, photos
   └─ troubleshooting.md       # Common issues
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
7. Run the daemon manually for a quick test:
   ```bash
   python3 daemon/soundtrigger.py
   ```
8. Install as a service (optional):
   ```bash
   sudo cp systemd/soundtrigger.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now soundtrigger.service
   sudo systemctl status soundtrigger.service
   ```

## Configuration (`config/mappings.json`)
- **activeProfile**: the profile name to use.
- **device.serial**: serial device path for Pico (e.g., `/dev/ttyACM0`).
- **device.aplayDevice**: ALSA device for `aplay` (e.g., `plughw:0,0` for USB DAC).
- **profiles[<name>].baseDir**: absolute path to profile sound directory.
- **profiles[<name>].ledButtons**: array of button IDs that have LEDs.
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
      "ledButtons": [1, 7, 9, 15],
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
      "ledButtons": [1, 7, 9, 15],
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

## Systemd Service
- Unit file at `systemd/soundtrigger.service` starts the daemon at boot.
- It sets `SOUND_MACHINE_CONFIG` to point at `config/mappings.json`.

## Performance Features
- **Sound Interruption**: New button presses immediately stop current playback for responsive switching
- **Optimized Debouncing**: 20ms debounce window for maximum responsiveness
- **Rapid Button Handling**: System handles rapid button mashing without getting confused
- **LED Management**: Proper LED feedback with background cleanup
- **Kid-Friendly**: Designed to handle enthusiastic button pressing without lockups

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
- **Audio Format Errors**: If you see "Sample format non available" errors, the daemon now uses simplified aplay commands that handle format conversion automatically.
- **Cheap Arcade Buttons**: The system now uses 50ms debouncing to handle multiple presses from cheap arcade buttons.
- **Serial Stability**: Improved serial communication with better timeouts and error handling for disconnections.
- **Pico Reset**: If the Pico stops responding, send reset commands: `python3 -c "import serial; ser=serial.Serial('/dev/ttyACM0', 115200); ser.write(b'\x03\x04'); ser.close()"`
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

# sound-machine
