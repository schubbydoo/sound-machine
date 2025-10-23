# boot.py - MicroPython boot configuration for Sound Machine Pico
# Simple boot configuration without usb_cdc dependency

print("Sound Machine Pico booting...")

# Try to enable USB CDC if available, but don't fail if not
try:
    import usb_cdc
    usb_cdc.enable(console=True, data=True)
    print("USB CDC enabled")
except ImportError:
    print("USB CDC not available - using default USB configuration")

# Try to disable USB HID to free up resources
try:
    import usb_hid
    usb_hid.disable()
    print("USB HID disabled")
except ImportError:
    print("USB HID not available")

print("Boot complete")
