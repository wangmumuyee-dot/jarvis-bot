from __future__ import annotations

import unittest

from app.security.sensitive import detect_sensitive


class SensitiveDetectionTest(unittest.TestCase):
    def test_detect_id_card(self) -> None:
        match = detect_sensitive("我身份证号是 110101199001011234，帮我记一下")
        assert match is not None
        self.assertEqual(match.kind, "id_card")

    def test_detect_bank_card_with_keyword(self) -> None:
        match = detect_sensitive("我的银行卡 6222020202020202020")
        assert match is not None
        self.assertIn(match.kind, {"bank_card", "password"})

    def test_detect_password(self) -> None:
        match = detect_sensitive("我的密码是 abc123，帮我存一下")
        assert match is not None
        self.assertEqual(match.kind, "password")

    def test_detect_api_key(self) -> None:
        match = detect_sensitive("api_key=sk-testtesttesttesttesttesttest")
        assert match is not None
        self.assertEqual(match.kind, "api_key")

    def test_normal_text_is_allowed(self) -> None:
        self.assertIsNone(detect_sensitive("今天午饭 38"))

    def test_route_blocks_sensitive_text_before_intent_parser(self) -> None:
        import app.main as main

        original_parser = main.intent_parser

        class ExplodingParser:
            def parse(self, _text: str):
                raise AssertionError("intent parser should not be called")

        try:
            main.intent_parser = ExplodingParser()  # type: ignore[assignment]
            reply = main.route_text("我的密码是 abc123，帮我存一下")
            self.assertIn("不会发送给 AI", reply)
        finally:
            main.intent_parser = original_parser


if __name__ == "__main__":
    unittest.main()
