"""Fernet encryption utilities for API key storage.

Encrypts/decrypts sensitive strings using a machine-specific key
derived from hostname + data directory via PBKDF2.
"""

from __future__ import annotations

import base64
import hashlib
import platform
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _derive_key(seed: str) -> bytes:
    """Derive a 32-byte Fernet key from a seed string via PBKDF2."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        seed.encode("utf-8"),
        salt=b"g-lab-key-derive-v1",
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(dk[:32])


def _default_seed() -> str:
    """Build a machine-specific seed from hostname + default data dir."""
    hostname = platform.node() or "localhost"
    data_dir = str(Path("/data").resolve())
    return f"{hostname}:{data_dir}"


def encrypt_key(plaintext: str, seed: str | None = None) -> str:
    """Encrypt a plaintext string and return a base64 ciphertext.

    Args:
        plaintext: The string to encrypt (e.g. an API key).
        seed: Optional custom seed. Defaults to machine-specific seed.

    Returns:
        Fernet-encrypted ciphertext as a string.
    """
    key = _derive_key(seed or _default_seed())
    fernet = Fernet(key)
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_key(ciphertext: str, seed: str | None = None) -> str:
    """Decrypt a Fernet ciphertext back to plaintext.

    Args:
        ciphertext: The encrypted string.
        seed: Optional custom seed (must match the one used for encryption).

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If decryption fails (wrong key or corrupted data).
    """
    key = _derive_key(seed or _default_seed())
    fernet = Fernet(key)
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt — wrong key or corrupted data") from exc
