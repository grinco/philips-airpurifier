"""Encryption helpers for the Philips encrypted HTTP (/di/v1) protocol.

The older Philips purifiers (AC2729, AC2889, AC3829, ...) negotiate an AES
session key with a Diffie-Hellman exchange and then exchange AES-128-CBC
(zero IV, PKCS#7) encrypted, base64 encoded JSON payloads.
"""

from __future__ import annotations

import base64
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# pylint: disable=line-too-long
G = int("A4D1CBD5C3FD34126765A442EFB99905F8104DD258AC507FD6406CFF14266D31266FEA1E5C41564B777E690F5504F213160217B4B01B886A5E91547F9E2749F4D7FBD7D3B9A92EE1909D0D2263F80A76A6A24C087A091F531DBF0A0169B6A28AD662A4D18E73AFA32D779D5918D08BC8858F4DCEF97C2A24855E6EEB22B3B2E5", 16)
P = int("B10B8F96A080E01DDE92DE5EAE5D54EC52C99FBCFB06A3C69A6A9DCA52D23B616073E28675A23D189838EF1E2EE652C013ECB4AEA906112324975C3CD49B83BFACCBDD7D90C4BD7098488E9C219A73724EFFD6FAE5644738FAA31A4FF55BCCC0A151AF5F0DC8B4BD45BF37DF365C1A65E68CFDA76D4DA708DF1FB2BC2E4A4371", 16)
# pylint: enable=line-too-long

_IV = bytes(16)


def _cipher(key: bytes) -> Cipher:
    return Cipher(algorithms.AES(key), modes.CBC(_IV))


def aes_decrypt(data: bytes, key: bytes) -> bytes:
    """Raw AES-CBC decrypt without unpadding."""
    decryptor = _cipher(key).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def dh_private() -> tuple[int, int]:
    """Return a new (private, public) Diffie-Hellman pair."""
    a = secrets.randbits(256)
    return a, pow(G, a, P)


def derive_session_key(private: int, hellman: str, key: str) -> bytes:
    """Derive the AES session key from the device's handshake answer."""
    shared = pow(int(hellman, 16), private, P)
    shared_key = shared.to_bytes(128, byteorder="big")[:16]
    return aes_decrypt(bytes.fromhex(key), shared_key)[:16]


def encrypt(values: dict[str, Any], key: bytes) -> bytes:
    """Encrypt a dict of values for a PUT request."""
    data = ("AA" + json.dumps(values)).encode("ascii")
    padder = padding.PKCS7(128).padder()
    data = padder.update(data) + padder.finalize()
    encryptor = _cipher(key).encryptor()
    return base64.b64encode(encryptor.update(data) + encryptor.finalize())


def decrypt(data: str | bytes, key: bytes) -> str:
    """Decrypt a device response. Raises ValueError on a wrong key."""
    payload = aes_decrypt(base64.b64decode(data), key)
    unpadder = padding.PKCS7(128).unpadder()
    payload = unpadder.update(payload) + unpadder.finalize()
    return payload[2:].decode("ascii")
