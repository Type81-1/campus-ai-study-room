"""安全原语：口令哈希与令牌生成。

- 口令使用 PBKDF2-HMAC-SHA256 + 每用户独立盐，存储格式：
  `pbkdf2_sha256$迭代次数$盐(hex)$摘要(hex)`
- 令牌是随机串，数据库只存它的 SHA-256 摘要，即使库被拖走也无法直接复用
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

ALGORITHM = "pbkdf2_sha256"
# 生产默认 20 万次；测试可用 PBKDF2_ITERATIONS 调低以缩短用例耗时
ITERATIONS = 200_000
SALT_BYTES = 16
TOKEN_BYTES = 32


def current_iterations() -> int:
    try:
        return int(os.environ.get("PBKDF2_ITERATIONS") or ITERATIONS)
    except ValueError:
        return ITERATIONS


def hash_password(raw: str, iterations: int | None = None) -> str:
    iterations = iterations or current_iterations()
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"{ALGORITHM}${iterations}${salt}${digest.hex()}"


def is_hashed(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(f"{ALGORITHM}$")


def verify_password(raw: str, stored: str | None) -> bool:
    """校验口令；兼容历史明文数据（用于存量库平滑迁移）。"""
    if not stored:
        return False
    if not is_hashed(stored):
        return hmac.compare_digest(raw, stored)
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", raw.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
