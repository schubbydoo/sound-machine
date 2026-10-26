#!/usr/bin/env python3
"""Sidecar network monitor for the Memory Spark Station (shared netguard package).

Runs as its own service so it never competes with the audio stack and exactly one
monitor exists (the web UI runs several gunicorn workers). It only watches and
self-heals WiFi; the LED daemon and soundtrigger are untouched.

No host is required: playback is local. The cloud library (kiosk downloads) is optional,
so an unreachable cloud never marks the network unusable. A link / gateway / internet
outage still counts, because the web UI and the phone app ride the same WiFi.
"""
import os
import signal
import sys
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NETGUARD_DIR = os.environ.get("NETGUARD_DIR", str(Path.home() / "netguard"))
sys.path.insert(0, NETGUARD_DIR)

import netguard  # noqa: E402

OPTIONAL_HOSTS = ["api.memorysparkplay.fun"]
HOTSPOT_PROFILES = ("PropManager-AP",)
GRACE = {"NO_LINK": 30, "NO_GATEWAY": 30, "NO_INTERNET": 30}
COOLDOWN = 60
STATE_DIR = BASE_DIR / "log" / "netguard"


def main() -> None:
    mon = netguard.Monitor(
        hosts=[], optional_hosts=OPTIONAL_HOSTS, state_dir=str(STATE_DIR),
        use_sudo=True, grace=GRACE, cooldown=COOLDOWN, hotspot_profiles=HOTSPOT_PROFILES)
    mon.start()
    done = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: done.set())
    done.wait()
    mon.stop()


if __name__ == "__main__":
    main()
