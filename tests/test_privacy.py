"""Privacy helpers: secret detection and clipboard preview redaction."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wt.util import (clip_preview_safe, is_high_entropy,  # noqa: E402
                     is_probably_sensitive)


class SensitiveTests(unittest.TestCase):
    def test_private_key(self):
        text = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
        self.assertTrue(is_probably_sensitive(text))

    def test_password_assignment(self):
        self.assertTrue(is_probably_sensitive("password=Hunter2Hunter2"))
        self.assertTrue(is_probably_sensitive("api_key: sk-live-abcdef123456"))

    def test_jwt(self):
        token = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                 "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                 "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
        self.assertTrue(is_probably_sensitive(token))

    def test_payment_card_luhn(self):
        self.assertTrue(is_probably_sensitive("卡号 4111 1111 1111 1111 请核对"))
        self.assertFalse(is_probably_sensitive("订单号 20261110001"))

    def test_national_id(self):
        self.assertTrue(is_probably_sensitive("身份证 11010519491231002X"))

    def test_normal_business_text(self):
        self.assertFalse(is_probably_sensitive("华东贸易 2026 年 11 月对账单，请核对金额"))
        self.assertFalse(is_probably_sensitive("明天 10 点开会，讨论 Q4 预算"))

    def test_high_entropy_token(self):
        token = "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7"
        self.assertTrue(is_high_entropy(token))
        self.assertFalse(is_high_entropy("这是正常的一句中文说明文字，不是随机串"))

    def test_preview_redaction(self):
        text, redacted = clip_preview_safe("订单号 A123 客户 华东贸易", 100)
        self.assertFalse(redacted)
        self.assertIn("华东贸易", text)
        text, redacted = clip_preview_safe("AKIAIOSFODNN7EXAMPLE", 100)
        self.assertTrue(redacted)
        self.assertEqual(text, "")
        text, redacted = clip_preview_safe("x" * 40, 10)
        self.assertFalse(redacted)
        self.assertTrue(text.endswith("\u2026"))


if __name__ == "__main__":
    unittest.main()
