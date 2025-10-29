# GPIO Pinout Reference for Sound Machine

## Raspberry Pi Zero GPIO Layout

```
       +3V3  +5V
        1     2
       GND    5V
        3     4
       GPIO17 GND
        5     6
       GPIO27 GPIO22
        7     8
       GPIO23 GPIO24
        9    10
       GPIO25 GPIO8
       11    12
       GPIO7  GND
       13    14
       GPIO0  GPIO1
       15    16
      GPIO14 GND
       17    18
      GPIO15 GPIO11
       19    20
      GPIO9  GND
       21    22
       GPIO11 GPIO2
       23    24
       GPIO3  GND
       25    26
```

## Current GPIO Assignments

### LED Control (New)
| Pin | GPIO | Purpose | Status |
|-----|------|---------|--------|
| 12  | 18   | LED Switch (PWM) | **IN USE** ✓ |

### Available Pins (PWM capable)
- GPIO 12
- GPIO 13
- GPIO 19
- GPIO 26

### Alternative PWM Pins (if GPIO 18 conflicts)
```bash
export LED_GPIO=12   # Pin 32 on header
export LED_GPIO=13   # Pin 33 on header
export LED_GPIO=19   # Pin 35 on header
export LED_GPIO=26   # Pin 37 on header
```

## Wiring Diagram

```
Raspberry Pi Zero              LED Switch
                               Circuit
     ┌─────────────┐
     │  GPIO 18    │─────────→ Signal In
     │  (Pin 12)   │
     │             │
     │  GND (Pin9) │─────────→ Ground
     └─────────────┘

Note: Physical pins on header differ from GPIO numbers (BCM)
GPIO 18 = Pin 12 on the 40-pin header
```

## GPIO Pin Quick Lookup

To find which physical pin corresponds to a GPIO number:

```
Physical Pin = GPIO number + 1 (approximate, check header diagram)

Exact mapping:
- GPIO 18 → Pin 12
- GPIO 12 → Pin 32
- GPIO 13 → Pin 33
- GPIO 19 → Pin 35
- GPIO 26 → Pin 37
```

Use `gpio readall` command to see full pinout:
```bash
sudo apt-get install wiringpi
gpio readall
```

## Notes

- All GPIO pins are 3.3V output
- Do NOT connect 5V directly to GPIO pins
- Use appropriate level shifting or protection for external circuits
- PWM is supported on most GPIO pins
