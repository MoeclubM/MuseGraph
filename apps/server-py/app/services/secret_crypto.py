import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

PREFIX = "enc:v1:"
SECRET_FIELD_NAMES = {
    "api_key",
    "secret",
    "private_key",
    "merchant_key",
    "signing_key",
    "key",
    "password",
    "token",
}


def _key() -> bytes:
    if not settings.SECRET_ENCRYPTION_KEY:
        raise RuntimeError("SECRET_ENCRYPTION_KEY is required for secret storage")
    try:
        key = base64.urlsafe_b64decode(settings.SECRET_ENCRYPTION_KEY)
    except Exception as exc:
        raise RuntimeError("SECRET_ENCRYPTION_KEY must be URL-safe base64") from exc
    if len(key) != 32:
        raise RuntimeError("SECRET_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def encrypt_secret(value: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value.startswith(PREFIX):
        raise RuntimeError("Stored secret is not encrypted")
    raw = base64.urlsafe_b64decode(value.removeprefix(PREFIX))
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def encrypt_secret_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [encrypt_secret_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    encrypted: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in SECRET_FIELD_NAMES and isinstance(item, str) and item:
            encrypted[key] = encrypt_secret(item)
        else:
            encrypted[key] = encrypt_secret_fields(item)
    return encrypted


def decrypt_secret_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [decrypt_secret_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    decrypted: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in SECRET_FIELD_NAMES and isinstance(item, str) and item:
            decrypted[key] = decrypt_secret(item)
        else:
            decrypted[key] = decrypt_secret_fields(item)
    return decrypted


def generate_encryption_key() -> str:
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
