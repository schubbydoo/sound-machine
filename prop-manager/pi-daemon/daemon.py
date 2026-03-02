#!/usr/bin/env python3
"""
Prop Manager BLE Daemon
GATT peripheral using the bless library.
Runs as a sidecar alongside the sound-machine service.
"""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timedelta
from typing import Optional

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

import wifi

# ── UUIDs ──────────────────────────────────────────────────────────────────
SERVICE_UUID    = "12345678-1234-1234-1234-123456789abc"
CHAR_PROP_INFO  = "12345678-1234-1234-1234-123456789ab1"
CHAR_AUTH       = "12345678-1234-1234-1234-123456789ab2"
CHAR_WIFI_CREDS = "12345678-1234-1234-1234-123456789ab3"
CHAR_COMMAND    = "12345678-1234-1234-1234-123456789ab4"
CHAR_STATUS     = "12345678-1234-1234-1234-123456789ab5"

CONFIG_PATH = "/etc/propmanager/config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("propmanager")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


class PropManagerDaemon:
    def __init__(self) -> None:
        self.config = load_config()
        self.authenticated = False
        self.wifi_ssid: Optional[str] = None
        self.wifi_password: Optional[str] = None
        self.server: Optional[BlessServer] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.boot_time = datetime.now()
        self.window_minutes: int = self.config.get("ble_advertise_window_minutes", 10)
        self._status: dict = {}
        # Discover the actual WebUI port at boot; fall back to config value
        self.webui_port: int = wifi.discover_webui_port(
            fallback=self.config.get("webui_port", 8080)
        )
        logger.info("WebUI port: %d", self.webui_port)
        self._update_initial_status()

    # ── State ───────────────────────────────────────────────────────────────

    def _update_initial_status(self) -> None:
        """Query current WiFi state at boot so clients see it immediately."""
        status = wifi.get_status()
        if status["connected"]:
            self._status = {
                "state": "wifi_connected",
                "ssid": status.get("ssid", ""),
                "ip": status.get("ip", ""),
            }
            logger.info(
                "Boot: already connected to %s at %s",
                status.get("ssid"),
                status.get("ip"),
            )
        else:
            self._status = {"state": "idle"}
            logger.info("Boot: not connected to WiFi")

    @property
    def advertising_window_open(self) -> bool:
        if self.window_minutes == 0:
            return True
        return datetime.now() - self.boot_time < timedelta(minutes=self.window_minutes)

    def set_status(self, state: str, **kwargs) -> None:
        self._status = {"state": state, **kwargs}
        logger.info("Status → %s", self._status)
        self._notify_status()

    def _status_bytes(self) -> bytearray:
        return bytearray(json.dumps(self._status).encode())

    def _refresh_webui_port(self) -> None:
        """Verify the cached port still responds; rediscover if not."""
        import socket
        try:
            with socket.create_connection(("127.0.0.1", self.webui_port), timeout=0.5) as s:
                s.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                if s.recv(4).startswith(b"HTTP"):
                    return  # still valid
        except OSError:
            pass
        new_port = wifi.discover_webui_port(fallback=self.config.get("webui_port", 8080))
        if new_port != self.webui_port:
            logger.info("WebUI port updated: %d → %d", self.webui_port, new_port)
            self.webui_port = new_port

    def _prop_info_bytes(self) -> bytearray:
        return bytearray(
            json.dumps(
                {"name": self.config["prop_name"], "port": self.webui_port}
            ).encode()
        )

    def _notify_status(self) -> None:
        if self.server is None:
            return
        try:
            char = self.server.get_characteristic(CHAR_STATUS)
            char.value = self._status_bytes()
            self.server.update_value(SERVICE_UUID, CHAR_STATUS)
        except Exception as exc:
            logger.warning("notify failed: %s", exc)

    # ── GATT handlers ───────────────────────────────────────────────────────

    def handle_read(
        self, characteristic: BlessGATTCharacteristic, **kwargs
    ) -> bytearray:
        uid = str(characteristic.uuid).lower()
        if uid == CHAR_PROP_INFO:
            self._refresh_webui_port()
            return self._prop_info_bytes()
        if uid == CHAR_STATUS:
            return self._status_bytes()
        return bytearray()

    async def handle_write(
        self, characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs
    ) -> None:
        uid = str(characteristic.uuid).lower()
        data = bytes(value).decode("utf-8", errors="replace").strip("\x00")
        logger.info("Write → %s : %s", uid, data)

        if not self.advertising_window_open:
            logger.warning("Write rejected: advertising window closed")
            return

        if uid == CHAR_AUTH:
            await self._handle_auth(data)
        elif uid == CHAR_WIFI_CREDS:
            if not self.authenticated:
                logger.warning("Rejected WiFi creds: not authenticated")
                return
            await self._handle_wifi_creds(data)
        elif uid == CHAR_COMMAND:
            if not self.authenticated:
                logger.warning("Rejected command: not authenticated")
                return
            await self._handle_command(data)

    async def _handle_auth(self, data: str) -> None:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            self.set_status("auth_failed")
            return

        if payload.get("access_code") == self.config["access_code"]:
            self.authenticated = True
            self.set_status("auth_ok")
            logger.info("Authentication successful")
        else:
            self.authenticated = False
            self.set_status("auth_failed")
            logger.warning("Authentication failed")

    async def _handle_wifi_creds(self, data: str) -> None:
        try:
            payload = json.loads(data)
            self.wifi_ssid = payload.get("ssid")
            self.wifi_password = payload.get("password")
            self.set_status("credentials_received")
            logger.info("Credentials received for SSID: %s", self.wifi_ssid)
        except json.JSONDecodeError:
            logger.error("Failed to parse WiFi credentials JSON")

    async def _handle_command(self, command: str) -> None:
        command = command.strip().strip('"')
        logger.info("Command: %s", command)

        if command == "connect_wifi":
            await self._connect_wifi()
        elif command == "disconnect_wifi":
            await self.loop.run_in_executor(None, wifi.disconnect)
            self.set_status("idle")
        elif command == "ap_mode":
            await self._enable_ap_mode()
        elif command == "reboot":
            logger.info("Rebooting system...")
            os.system("sudo reboot")

    async def _connect_wifi(self) -> None:
        if not self.wifi_ssid:
            logger.error("No SSID stored")
            self.set_status("wifi_failed")
            return

        prev_status = wifi.get_status()
        prev_ssid = prev_status.get("ssid") if prev_status["connected"] else None

        self.set_status("connecting")
        success, ip = await self.loop.run_in_executor(
            None, wifi.connect, self.wifi_ssid, self.wifi_password
        )

        if success and ip:
            self.set_status("wifi_connected", ssid=self.wifi_ssid, ip=ip)
            return

        logger.error("Failed to connect to %s", self.wifi_ssid)

        # Error recovery: fall back to last known-working SSID
        if prev_ssid and prev_ssid != self.wifi_ssid:
            logger.info("Attempting fallback to %s", prev_ssid)
            fb_ok, fb_ip = await self.loop.run_in_executor(
                None, wifi.connect_by_profile, prev_ssid
            )
            if fb_ok:
                self.set_status("wifi_connected", ssid=prev_ssid, ip=fb_ip)
                return

        self.set_status("wifi_failed")

    async def _enable_ap_mode(self) -> None:
        self.set_status("ap_mode", ip="192.168.4.1")
        ok = await self.loop.run_in_executor(None, wifi.enable_ap_mode)
        if not ok:
            logger.error("Failed to enable AP mode")

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _signal_handler(sig, _frame):
            logger.info("Signal %s received, shutting down", sig)
            self.loop.call_soon_threadsafe(stop_event.set)

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        self.server = BlessServer(
            name=self.config["prop_name"], loop=self.loop
        )
        self.server.read_request_func = self.handle_read
        self.server.write_request_func = self.handle_write

        await self.server.add_new_service(SERVICE_UUID)

        # Prop Info — Read
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_PROP_INFO,
            GATTCharacteristicProperties.read,
            self._prop_info_bytes(),
            GATTAttributePermissions.readable,
        )
        # Auth — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_AUTH,
            GATTCharacteristicProperties.write,
            None,
            GATTAttributePermissions.writeable,
        )
        # WiFi Credentials — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_WIFI_CREDS,
            GATTCharacteristicProperties.write,
            None,
            GATTAttributePermissions.writeable,
        )
        # Command — Write
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_COMMAND,
            GATTCharacteristicProperties.write,
            None,
            GATTAttributePermissions.writeable,
        )
        # Status — Read + Notify
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_STATUS,
            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            self._status_bytes(),
            GATTAttributePermissions.readable,
        )

        await self.server.start()

        window_str = (
            f"{self.window_minutes} min" if self.window_minutes > 0 else "always-on"
        )
        logger.info(
            "BLE daemon advertising as '%s' (window: %s)",
            self.config["prop_name"],
            window_str,
        )
        logger.info("Initial status: %s", self._status)

        await stop_event.wait()

        await self.server.stop()
        logger.info("BLE daemon stopped cleanly")


if __name__ == "__main__":
    asyncio.run(PropManagerDaemon().run())
