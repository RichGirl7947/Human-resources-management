from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import hmac
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .config import get_settings


ENCRYPTED_PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet | None:
    key = get_settings().data_encryption_key
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("HR_DATA_ENCRYPTION_KEY 必须是有效的 Fernet Key") from exc


def encrypt_value(value: str | None) -> str | None:
    if value is None or value.startswith(ENCRYPTED_PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        if get_settings().environment == "production":
            raise RuntimeError("生产环境必须配置 HR_DATA_ENCRYPTION_KEY")
        return value
    token = cipher.encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_value(value: str | None) -> str | None:
    if value is None or not value.startswith(ENCRYPTED_PREFIX):
        return value
    cipher = _fernet()
    if cipher is None:
        raise RuntimeError("无法解密个人数据：未配置 HR_DATA_ENCRYPTION_KEY")
    try:
        return cipher.decrypt(value[len(ENCRYPTED_PREFIX) :].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("个人数据解密失败，请检查加密密钥") from exc


def pii_hash(value: str) -> str:
    settings = get_settings()
    secret = settings.data_encryption_key or settings.jwt_secret
    if not secret:
        if settings.environment == "production":
            raise RuntimeError("生产环境缺少个人数据哈希密钥")
        secret = "development-only-pii-hash-key"
    normalized = value.strip().casefold().encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), normalized, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class EncryptedText(TypeDecorator[str]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return encrypt_value(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return decrypt_value(value)


class EncryptedJSON(TypeDecorator[Any]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: object) -> str | None:
        if value is None:
            return None
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return encrypt_value(serialized)

    def process_result_value(self, value: Any, dialect: object) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        decrypted = decrypt_value(str(value))
        try:
            return json.loads(decrypted or "null")
        except json.JSONDecodeError:
            return decrypted
