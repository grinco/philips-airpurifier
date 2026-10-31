"""A fake Philips purifier speaking the encrypted HTTP (/di/v1) protocol."""

from __future__ import annotations

import copy
import json
import secrets
import socket
from typing import Any

from aiohttp import web
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.philips_airpurifier.crypto import G, P, decrypt, encrypt

AC2889_STATUS = {
    "om": "2", "pwr": "1", "cl": False, "aqil": 100, "uil": "1", "dt": 0,
    "dtrs": 0, "mode": "M", "pm25": 3, "iaql": 1, "aqit": 7, "ddp": "0", "err": 0,
}
AC2889_FILTERS = {"fltt1": "A6", "fltt2": "C9", "fltsts0": 62, "fltsts1": 7111, "fltsts2": 8551}

AC3829_STATUS = {
    **AC2889_STATUS, "func": "PH", "rh": 45, "rhset": 50, "temp": 22, "wl": 100, "mode": "P",
}
AC3829_FILTERS = {**AC2889_FILTERS, "wicksts": 4800}


class FakePurifier:
    """In-process purifier. Toggle `failing` to make it stop answering."""

    def __init__(
        self,
        model: str = "AC2889_10",
        mac: str = "e8:c1:d7:00:73:b8",
        status: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.mac = mac
        self.status = copy.deepcopy(status or AC2889_STATUS)
        self.filters = copy.deepcopy(filters or AC2889_FILTERS)
        self.failing = False
        self.key: bytes | None = None
        self.handshakes = 0
        self.puts: list[dict[str, Any]] = []
        self._runner: web.AppRunner | None = None
        self._sock: socket.socket | None = None
        self.host = ""

    def reboot(self) -> None:
        """Forget the session key, like a power cycle does."""
        self.key = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_put("/di/v1/products/0/security", self._security)
        app.router.add_get("/di/v1/products/0/firmware", self._getter(self._firmware))
        app.router.add_get("/di/v1/products/0/wifi", self._getter(self._wifi))
        app.router.add_get("/di/v1/products/1/air", self._getter(lambda: self.status))
        app.router.add_get("/di/v1/products/1/fltsts", self._getter(lambda: self.filters))
        app.router.add_put("/di/v1/products/1/air", self._put_air)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        # Pre-bound socket: no executor/DNS lookup, and a fixed port on restart.
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("127.0.0.1", 0))
            self.host = f"127.0.0.1:{self._sock.getsockname()[1]}"
        await web.SockSite(self._runner, self._sock).start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _firmware(self) -> dict[str, Any]:
        return {"name": self.model, "version": "14", "upgrade": "", "state": "idle"}

    def _wifi(self) -> dict[str, Any]:
        return {"ssid": "test", "macaddress": self.mac, "dhcp": True}

    def _check(self) -> None:
        if self.failing:
            raise web.HTTPServiceUnavailable

    async def _security(self, request: web.Request) -> web.Response:
        self._check()
        body = json.loads(await request.text())
        a_pub = int(body["diffie"], 16)
        b = secrets.randbits(256)
        shared = pow(a_pub, b, P).to_bytes(128, "big")[:16]
        self.key = secrets.token_bytes(16)
        enc = Cipher(algorithms.AES(shared), modes.CBC(bytes(16))).encryptor()
        key_hex = (enc.update(self.key) + enc.finalize()).hex()
        self.handshakes += 1
        return web.json_response({"hellman": format(pow(G, b, P), "x"), "key": key_hex})

    def _encrypted(self, values: dict[str, Any]) -> web.Response:
        # A device without a key (rebooted) answers with garbage for the client.
        key = self.key or secrets.token_bytes(16)
        return web.Response(text=encrypt(values, key).decode("ascii"))

    def _getter(self, fn):
        async def handler(request: web.Request) -> web.Response:
            self._check()
            return self._encrypted(fn())

        return handler

    async def _put_air(self, request: web.Request) -> web.Response:
        self._check()
        if self.key is None:
            raise web.HTTPBadRequest
        values = json.loads(decrypt(await request.text(), self.key))
        self.puts.append(values)
        self.status.update(values)
        return self._encrypted(self.status)
