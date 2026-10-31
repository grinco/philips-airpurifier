"""Crypto helpers."""

from custom_components.philips_airpurifier.crypto import (
    G, P, decrypt, derive_session_key, dh_private, encrypt,
)

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def test_roundtrip() -> None:
    key = bytes(range(16))
    values = {"pwr": "1", "mode": "M", "om": "t"}
    assert decrypt(encrypt(values, key), key) == '{"pwr": "1", "mode": "M", "om": "t"}'


def test_key_exchange() -> None:
    private, public = dh_private()
    device_private = 12345678901234567890
    shared = pow(public, device_private, P).to_bytes(128, "big")[:16]
    session = bytes(range(16, 32))
    enc = Cipher(algorithms.AES(shared), modes.CBC(bytes(16))).encryptor()
    key_hex = (enc.update(session) + enc.finalize()).hex()
    hellman = format(pow(G, device_private, P), "x")
    assert derive_session_key(private, hellman, key_hex) == session
