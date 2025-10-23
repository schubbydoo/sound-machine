# boot.py - MicroPython boot configuration for Sound Machine Pico
# This file runs on every boot and enables USB CDC

import usb_cdc
import usb_hid

# Enable USB CDC (serial communication)
usb_cdc.enable(console=True, data=True)

# Disable USB HID to free up resources (we don't need keyboard/mouse)
usb_hid.disable()

print("USB CDC enabled for Sound Machine")
