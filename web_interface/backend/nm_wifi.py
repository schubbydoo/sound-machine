"""
nm_wifi.py — canonical NetworkManager WiFi utilities for all props.

Writes credentials as NM keyfiles directly to /etc/NetworkManager/system-connections/,
bypassing netplan routing to /run (tmpfs).  All props use this module so
WiFi management is consistent across Sound Console, Psychic Hotline, and Zoltar.
"""

import os
import re
import subprocess
import uuid as _uuid_module
from typing import Optional

_NM_DIR = "/etc/NetworkManager/system-connections"


def _run(cmd: list, timeout: int = 30) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def save_credentials(ssid: str, password: str) -> tuple[bool, str]:
    """
    Write a WPA-PSK NM keyfile directly to /etc/NetworkManager/system-connections/.
    Preserves existing UUID if a profile for this SSID already exists.
    Reloads NM so it picks up the new file.
    Returns (success, message).
    """
    safe_name = ssid.replace("/", "_").replace(" ", "_")
    filepath = os.path.join(_NM_DIR, f"{safe_name}.nmconnection")

    # Preserve existing UUID if the file is readable
    existing_uuid = None
    rc, out, _ = _run(["sudo", "cat", filepath])
    if rc == 0:
        for line in out.splitlines():
            if line.startswith("uuid="):
                existing_uuid = line.split("=", 1)[1].strip()
                break

    conn_uuid = existing_uuid or str(_uuid_module.uuid4())

    keyfile = (
        "[connection]\n"
        f"id={ssid}\n"
        f"uuid={conn_uuid}\n"
        "type=wifi\n"
        "autoconnect=true\n"
        "autoconnect-priority=10\n"
        "\n"
        "[wifi]\n"
        "mode=infrastructure\n"
        f"ssid={ssid}\n"
        "\n"
        "[wifi-security]\n"
        "auth-alg=open\n"
        "key-mgmt=wpa-psk\n"
        f"psk={password}\n"
        "\n"
        "[ipv4]\n"
        "method=auto\n"
        "\n"
        "[ipv6]\n"
        "addr-gen-mode=default\n"
        "method=auto\n"
    )

    # Write via sudo tee — works whether caller is root or a sudoers user
    try:
        result = subprocess.run(
            ["sudo", "tee", filepath],
            input=keyfile,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, f"Failed to write keyfile: {result.stderr}"
        subprocess.run(["sudo", "chmod", "600", filepath], check=True)
    except Exception as exc:
        return False, f"Failed to write keyfile: {exc}"

    _run(["sudo", "nmcli", "connection", "reload"])
    return True, f"Profile saved for {ssid}"


def list_known() -> dict:
    """
    Return known WiFi profiles from NM:
      {ssid: {"password": "", "auto": bool, "priority": int}}
    """
    rc, out, _ = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    wifi_names = []
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1] in ("wifi", "802-11-wireless"):
            wifi_names.append(parts[0])

    known = {}
    for name in wifi_names:
        rc2, out2, _ = _run(
            ["nmcli", "-t", "-f",
             "connection.autoconnect,connection.autoconnect-priority",
             "connection", "show", name]
        )
        auto = False
        priority = 0
        for line in out2.splitlines():
            if line.startswith("connection.autoconnect:"):
                auto = line.split(":", 1)[1].strip().lower() in ("yes", "true")
            elif line.startswith("connection.autoconnect-priority:"):
                try:
                    priority = int(line.split(":", 1)[1].strip())
                except ValueError:
                    priority = 0
        known[name] = {"password": "", "auto": auto, "priority": priority}

    return known


def scan() -> list:
    """Return nearby WiFi networks sorted by signal strength."""
    _run(["nmcli", "dev", "wifi", "rescan"])
    rc, out, _ = _run(["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi", "list"])
    if not out.strip():
        rc, out, _ = _run(["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi"])
    nets = []
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid, sec, sig = parts[0], parts[1], parts[2]
        if not ssid:
            continue
        try:
            nets.append({"ssid": ssid, "security": sec, "signal": int(sig or 0)})
        except ValueError:
            continue
    best: dict = {}
    for n in nets:
        if n["ssid"] not in best or n["signal"] > best[n["ssid"]]["signal"]:
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda x: -x["signal"])


def _get_profile_uuid(ssid: str) -> Optional[str]:
    """Return UUID of the first NM WiFi profile matching ssid, or None."""
    rc, out, _ = _run(["nmcli", "-t", "-f", "UUID,NAME,TYPE", "connection", "show"])
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[2] in ("wifi", "802-11-wireless") and parts[1] == ssid:
            return parts[0]
    return None


def connect(ssid: str, password: str = "") -> str:
    """Connect to WiFi. Uses existing NM profile if one exists for this SSID."""
    uuid = _get_profile_uuid(ssid)
    if uuid:
        rc, out, err = _run(["nmcli", "connection", "up", uuid])
        return out or err
    if password:
        rc, out, err = _run(["nmcli", "dev", "wifi", "connect", ssid, "password", password])
    else:
        rc, out, err = _run(["nmcli", "dev", "wifi", "connect", ssid])
    return out or err


def forget(ssid: str) -> str:
    """Delete the NM WiFi profile for ssid."""
    uuid = _get_profile_uuid(ssid)
    if uuid:
        rc, out, err = _run(["sudo", "nmcli", "connection", "delete", uuid])
        return out or err
    return "No connection found"


def set_autopref(ssid: str, auto: bool, priority: int) -> str:
    """Update autoconnect settings for an existing NM profile."""
    uuid = _get_profile_uuid(ssid)
    if not uuid:
        return "No connection found to modify"
    auto_val = "yes" if auto else "no"
    _run(["sudo", "nmcli", "connection", "modify", uuid, "connection.autoconnect", auto_val])
    _run(["sudo", "nmcli", "connection", "modify", uuid,
          "connection.autoconnect-priority", str(priority)])
    return "OK"


def get_status() -> dict:
    """Return current WiFi connection status for wlan0."""
    rc, out, _ = _run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"])
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "wlan0" and "connected" in parts[1]:
            return {"connected": True, "ssid": _get_connected_ssid(), "ip": _get_ip()}
    return {"connected": False}


def _get_connected_ssid() -> str:
    rc, out, _ = _run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0] == "yes":
            return parts[1]
    return ""


def _get_ip(iface: str = "wlan0") -> str:
    rc, out, _ = _run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", iface])
    for line in out.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)", line)
        if match:
            return match.group(1)
    return ""
