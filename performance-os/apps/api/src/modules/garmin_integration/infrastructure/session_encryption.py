"""
Encrypts the serialized garminconnect token-file contents before it's
persisted to provider_connections.access_token, and decrypts it on read.

Uses Fernet (symmetric, authenticated encryption) with a key from app
config — NOT hardcoded, NOT derived from anything request-specific.
Rotate this key via a standard key-rotation runbook if it's ever
suspected of being compromised; every stored session would need to be
re-encrypted or users re-connected.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from core.config import get_settings  # app-wide settings, holds the encryption key


class SessionEncryptor:
    def __init__(self) -> None:
        settings = get_settings()
        self._fernet = Fernet(settings.garmin_session_encryption_key)

    def encrypt(self, plaintext_session_blob: str) -> str:
        return self._fernet.encrypt(plaintext_session_blob.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
