"""单元测试：口令哈希与令牌原语。"""
from __future__ import annotations

import unittest

from tests import base  # noqa: F401

from backend.security import (
    ALGORITHM,
    hash_password,
    is_hashed,
    new_token,
    token_digest,
    verify_password,
)


class PasswordHashTest(unittest.TestCase):
    def test_hash_format(self):
        hashed = hash_password("123456", iterations=1000)
        parts = hashed.split("$")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], ALGORITHM)
        self.assertEqual(parts[1], "1000")
        self.assertEqual(len(parts[2]), 32)   # 16 字节盐的 hex
        self.assertEqual(len(parts[3]), 64)   # sha256 的 hex

    def test_same_password_different_salt(self):
        first = hash_password("123456", iterations=1000)
        second = hash_password("123456", iterations=1000)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("123456", first))
        self.assertTrue(verify_password("123456", second))

    def test_verify_rejects_wrong_password(self):
        hashed = hash_password("123456", iterations=1000)
        self.assertFalse(verify_password("123457", hashed))
        self.assertFalse(verify_password("", hashed))

    def test_verify_legacy_plaintext(self):
        """存量明文库要能登录，且在首次登录时被升级。"""
        self.assertFalse(is_hashed("123456"))
        self.assertTrue(verify_password("123456", "123456"))
        self.assertFalse(verify_password("bad", "123456"))

    def test_is_hashed_flag(self):
        self.assertTrue(is_hashed(hash_password("x", iterations=1000)))
        self.assertFalse(is_hashed(""))
        self.assertFalse(is_hashed(None))

    def test_broken_hash_returns_false(self):
        self.assertFalse(verify_password("123456", "pbkdf2_sha256$bad$data$here"))


class TokenTest(unittest.TestCase):
    def test_token_is_random_and_long(self):
        first, second = new_token(), new_token()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 40)

    def test_digest_is_stable_and_not_reversible(self):
        token = new_token()
        self.assertEqual(token_digest(token), token_digest(token))
        self.assertEqual(len(token_digest(token)), 64)
        self.assertNotEqual(token_digest(token), token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
