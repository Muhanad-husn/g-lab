"""Unit tests for Fernet encryption utilities."""

from __future__ import annotations

import pytest

from app.utils.crypto import decrypt_key, encrypt_key


def test_round_trip() -> None:
    """Encrypt then decrypt returns original plaintext."""
    seed = "test-seed-1234"
    plaintext = "sk-or-abc123xyz"

    ciphertext = encrypt_key(plaintext, seed=seed)
    assert ciphertext != plaintext
    assert decrypt_key(ciphertext, seed=seed) == plaintext


def test_different_seeds_different_ciphertext() -> None:
    """Same plaintext encrypted with different seeds produces different ciphertext."""
    plaintext = "my-secret-key"
    ct1 = encrypt_key(plaintext, seed="seed-alpha")
    ct2 = encrypt_key(plaintext, seed="seed-beta")
    assert ct1 != ct2


def test_wrong_seed_fails() -> None:
    """Decrypting with wrong seed raises ValueError."""
    ciphertext = encrypt_key("secret", seed="correct-seed")
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_key(ciphertext, seed="wrong-seed")


def test_default_seed_round_trip() -> None:
    """Round-trip with default (machine-specific) seed."""
    plaintext = "sk-or-default-test"
    ct = encrypt_key(plaintext)
    assert decrypt_key(ct) == plaintext


def test_empty_string_round_trip() -> None:
    """Empty strings should encrypt/decrypt correctly."""
    ct = encrypt_key("", seed="test")
    assert decrypt_key(ct, seed="test") == ""


def test_unicode_round_trip() -> None:
    """Unicode content should survive encrypt/decrypt."""
    plaintext = "api-key-🔑-über"
    ct = encrypt_key(plaintext, seed="uni")
    assert decrypt_key(ct, seed="uni") == plaintext
