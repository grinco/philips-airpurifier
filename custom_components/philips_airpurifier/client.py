"""Async client for Philips air purifiers speaking the encrypted HTTP protocol."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .crypto import decrypt, derive_session_key, dh_private, encrypt

_LOGGER = logging.getLogger(__name__)

PATH_SECURITY = "/di/v1/products/0/security"
PATH_FIRMWARE = "/di/v1/products/0/firmware"
PATH_WIFI = "/di/v1/products/0/wifi"
PATH_AIR = "/di/v1/products/1/air"
PATH_FILTERS = "/di/v1/products/1/fltsts"

DEFAULT_TIMEOUT = 10


class PhilipsError(Exception):
    """Base error for the Philips client."""


class PhilipsConnectionError(PhilipsError):
    """The device could not be reached or did not answer properly."""


class PhilipsAirClient:
    """Talks to one purifier.

    The device firmware handles only one request at a time and gets confused
    by kept-alive connections, so every request uses a fresh connection and
    requests are serialised with a lock. Any failure drops the session key,
    which forces a new key exchange on the next request.
    """

    def __init__(self, host: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.host = host
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._key: bytes | None = None
        self._lock = asyncio.Lock()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(force_close=True, limit=1),
                timeout=self._timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._key = None

    async def reset(self) -> None:
        """Forget the session key and drop the HTTP session."""
        await self.close()

    def _url(self, path: str) -> str:
        return f"http://{self.host}{path}"

    async def _raw(self, method: str, path: str, data: bytes | None = None) -> str:
        try:
            async with self._get_session().request(
                method, self._url(path), data=data
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
            raise PhilipsConnectionError(
                f"{method} {path} failed: {err!r}"
            ) from err

    async def _handshake(self) -> None:
        private, public = dh_private()
        body = json.dumps({"diffie": format(public, "x")}).encode("ascii")
        text = await self._raw("PUT", PATH_SECURITY, body)
        try:
            answer = json.loads(text)
            self._key = derive_session_key(private, answer["hellman"], answer["key"])
        except (ValueError, KeyError, TypeError) as err:
            raise PhilipsConnectionError(f"Invalid handshake answer: {err}") from err
        _LOGGER.debug("%s: new session key negotiated", self.host)

    async def _encrypted_once(
        self, method: str, path: str, values: dict[str, Any] | None
    ) -> dict[str, Any]:
        if self._key is None:
            await self._handshake()
        assert self._key is not None
        body = encrypt(values, self._key) if values is not None else None
        text = await self._raw(method, path, body)
        try:
            return json.loads(decrypt(text, self._key))
        except (ValueError, UnicodeDecodeError) as err:
            # Most likely the device rebooted and forgot our key.
            self._key = None
            raise PhilipsConnectionError(f"Cannot decrypt answer: {err}") from err

    async def _encrypted(
        self, method: str, path: str, values: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with self._lock:
            try:
                return await self._encrypted_once(method, path, values)
            except PhilipsConnectionError as err:
                _LOGGER.debug("%s: %s, retrying with a new key", self.host, err)
                await self.reset()
            try:
                return await self._encrypted_once(method, path, values)
            except PhilipsConnectionError:
                await self.reset()
                raise

    async def get_status(self) -> dict[str, Any]:
        """Return the air/status values."""
        return await self._encrypted("GET", PATH_AIR)

    async def get_filters(self) -> dict[str, Any]:
        """Return the filter status values."""
        return await self._encrypted("GET", PATH_FILTERS)

    async def get_firmware(self) -> dict[str, Any]:
        """Return firmware info (contains the model name)."""
        return await self._encrypted("GET", PATH_FIRMWARE)

    async def get_wifi(self) -> dict[str, Any]:
        """Return wifi info (contains the MAC address)."""
        return await self._encrypted("GET", PATH_WIFI)

    async def set_values(self, values: dict[str, Any]) -> dict[str, Any]:
        """Write values; returns the new air/status values."""
        return await self._encrypted("PUT", PATH_AIR, values)
