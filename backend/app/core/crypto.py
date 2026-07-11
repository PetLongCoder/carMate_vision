"""用户隐私字段对称加密（AES-256-GCM，确定性 nonce，支持按明文查库）。"""

from __future__ import annotations

import base64
import hashlib
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

ENC_PREFIX = "enc:v1:"
_PHONE_RE = re.compile(r"^1\d{10}$")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _key_bytes() -> bytes:
    raw = settings.DATA_ENCRYPTION_KEY.encode("utf-8")
    return hashlib.sha256(raw).digest()


def _nonce(field: str, plaintext: str) -> bytes:
    digest = hashlib.sha256(_key_bytes() + field.encode("utf-8") + plaintext.encode("utf-8")).digest()
    return digest[:12]


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(ENC_PREFIX))


def encrypt_field(field: str, plaintext: str) -> str:
    text = plaintext.strip()
    if not text:
        return text
    if is_encrypted(text):
        return text
    nonce = _nonce(field, text)
    ciphertext = AESGCM(_key_bytes()).encrypt(nonce, text.encode("utf-8"), None)
    blob = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{ENC_PREFIX}{blob}"


def decrypt_field(field: str, stored: str) -> str:
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored
    raw = base64.urlsafe_b64decode(stored[len(ENC_PREFIX) :].encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_key_bytes()).decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    plain = phone if not is_encrypted(phone) else decrypt_field("phone", phone)
    if len(plain) >= 7:
        return f"{plain[:3]}****{plain[-4:]}"
    return plain


def mask_email(email: str | None) -> str | None:
    if not email:
        return None
    plain = email if not is_encrypted(email) else decrypt_field("email", email)
    local, sep, domain = plain.partition("@")
    if not sep:
        return plain
    if len(local) <= 2:
        masked_local = f"{local[0]}***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def looks_like_plain_phone(value: str | None) -> bool:
    return bool(value and _PHONE_RE.fullmatch(value))


def looks_like_plain_email(value: str | None) -> bool:
    return bool(value and _EMAIL_RE.fullmatch(value))
