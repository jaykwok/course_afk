import unittest
from datetime import datetime, timedelta

from core.auth.credential import (
    build_account_label,
    is_credential_expired,
    is_credential_expired_at,
)


class CredentialTests(unittest.TestCase):
    def test_credential_expired_after_28_days(self):
        saved_at = datetime(2026, 4, 1, 8, 0, 0)
        now = saved_at + timedelta(days=29)
        self.assertTrue(is_credential_expired(saved_at, now))

    def test_credential_still_valid_within_28_days(self):
        saved_at = datetime(2026, 4, 1, 8, 0, 0)
        now = saved_at + timedelta(days=27)
        self.assertFalse(is_credential_expired(saved_at, now))

    def test_credential_expired_on_expiration_date(self):
        expires_at = datetime(2026, 5, 19, 14, 34, 28)
        now = datetime(2026, 5, 19, 8, 0, 0)
        self.assertTrue(is_credential_expired_at(expires_at, now))

    def test_build_account_label_prefers_full_name(self):
        self.assertEqual(
            build_account_label("测试用户", "test_user"),
            "测试用户（test_user）",
        )
