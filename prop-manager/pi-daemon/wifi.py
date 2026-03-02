#!/usr/bin/env python3
"""
WiFi helper functions using nmcli (NetworkManager CLI).

Non-destructive: adds/updates connection profiles without deleting
existing ones (e.g. home network, shop network).
"""

import logging
import re
import subprocess
import time
from typing import Optional

logger = logging.getLogger("propmanager.wifi")

# Seconds to poll for an IP address after bringing up a connection
_IP_POLL_SECONDS = 30
_IP_POLL_INTERVAL = 2


def _run(cmd: list, timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _wait_for_ip(iface: str = "wlan0") -> Optional[str]:
    """Poll until an IP address is assigned or timeout."""
    attempts = _IP_POLL_SECONDS // _IP_POLL_INTERVAL
    for _ in range(attempts):
        time.sleep(_IP_POLL_INTERVAL)
        ip = get_ip_address(iface)
        if ip:
            return ip
    return None


# ── Status queries ──────────────────────────────────────────────────────────

def get_status() -> dict:
    """Return current WiFi connection status for wlan0."""
    rc, out, _ = _run(
        ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"]
    )
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "wlan0":
            if "connected" in parts[1]:
                return {
                    "connected": True,
                    "ssid": get_connected_ssid(),
                    "ip": get_ip_address(),
                }
    return {"connected": False}


def get_connected_ssid() -> str:
    """Return the SSID of the active WiFi connection."""
    rc, out, _ = _run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0] == "yes":
            return parts[1]
    return ""


def get_ip_address(iface: str = "wlan0") -> str:
    """Return the IPv4 address of the interface (without prefix length)."""
    rc, out, _ = _run(
        ["nmcli", "-g", "IP4.ADDRESS", "device", "show", iface]
    )
    for line in out.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)", line)
        if match:
            return match.group(1)
    return ""


def _get_wifi_profiles() -> list[str]:
    """Return list of existing WiFi connection profile names."""
    rc, out, _ = _run(
        ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"]
    )
    profiles = []
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1] == "wifi":
            profiles.append(parts[0])
    return profiles


# ── Connection management ───────────────────────────────────────────────────

def connect(ssid: str, password: str) -> tuple[bool, str]:
    """
    Connect to a WiFi network, creating or updating a profile.
    Never deletes existing profiles.
    Returns (success, ip_address).
    """
    logger.info("Connecting to SSID: %s", ssid)
    existing = _get_wifi_profiles()

    if ssid in existing:
        logger.info("Profile '%s' exists — updating password", ssid)
        rc, _, err = _run([
            "nmcli", "connection", "modify", ssid,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", password,
        ])
        if rc != 0:
            logger.error("modify failed: %s", err)
            return False, ""
        rc, _, err = _run(["nmcli", "connection", "up", ssid])
    else:
        logger.info("Creating new profile for '%s'", ssid)
        rc, _, err = _run([
            "nmcli", "device", "wifi", "connect", ssid,
            "password", password,
        ])

    if rc != 0:
        logger.error("nmcli connect failed: %s", err)
        return False, ""

    ip = _wait_for_ip()
    if ip:
        logger.info("Connected — IP: %s", ip)
        return True, ip

    logger.error("Timed out waiting for IP address")
    return False, ""


def connect_by_profile(profile_name: str) -> tuple[bool, str]:
    """
    Bring up an existing nmcli profile by name.
    Used for error-recovery fallback to last known-working network.
    """
    logger.info("Bringing up existing profile: %s", profile_name)
    rc, _, err = _run(["nmcli", "connection", "up", profile_name])
    if rc != 0:
        logger.error("Failed to bring up '%s': %s", profile_name, err)
        return False, ""

    ip = _wait_for_ip()
    if ip:
        return True, ip
    return False, ""


def disconnect() -> bool:
    """
    Disconnect from the current WiFi network.
    The connection profile is preserved for future use.
    """
    rc, _, err = _run(["nmcli", "device", "disconnect", "wlan0"])
    if rc != 0:
        logger.error("Disconnect failed: %s", err)
        return False
    logger.info("WiFi disconnected (profile preserved)")
    return True


def enable_ap_mode() -> bool:
    """
    Switch wlan0 to Access Point / hotspot mode via NetworkManager.
    Uses nmcli's built-in hotspot command — does not require hostapd separately.
    The hotspot profile is created fresh each time; it does not overwrite
    any existing station profiles.
    """
    logger.info("Enabling AP mode via nmcli hotspot...")

    # Remove a stale hotspot profile if it exists so nmcli recreates it cleanly
    _run(["nmcli", "connection", "delete", "PropManager-AP"])

    rc, _, err = _run([
        "nmcli", "device", "wifi", "hotspot",
        "ifname", "wlan0",
        "ssid", "PropManager-AP",
        "password", "propmanager",
        "con-name", "PropManager-AP",
    ], timeout=20)

    if rc != 0:
        logger.error("AP mode failed: %s", err)
        return False

    logger.info("AP mode active — IP: 192.168.4.1")
    return True
