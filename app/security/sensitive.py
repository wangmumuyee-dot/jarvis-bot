from __future__ import annotations

import re
from dataclasses import dataclass


SENSITIVE_REPLY = (
    "我检测到这条消息可能包含身份证、银行卡、密码或密钥等敏感信息。\n"
    "为保护隐私，我不会发送给 AI，也不会保存原文。\n"
    "请删除敏感信息后重新发送。"
)


@dataclass(frozen=True)
class SensitiveMatch:
    kind: str
    reason: str


ID_CARD_RE = re.compile(r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")
BANK_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){16,19}(?!\d)")
VERIFY_CODE_RE = re.compile(r"(?:验证码|校验码|短信码).{0,10}\d{4,8}")
API_KEY_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{20,}|"
    r"(?:api[_-]?key|secret|token|private[_-]?key)\s*[:=]\s*[A-Za-z0-9_./+=-]{12,})",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")

PASSWORD_KEYWORDS = [
    "密码",
    "password",
    "passwd",
    "pwd",
    "银行卡",
    "卡号",
    "身份证",
    "cvv",
    "cvc",
    "助记词",
    "私钥",
    "密钥",
]


def detect_sensitive(text: str) -> SensitiveMatch | None:
    normalized = text.strip()
    if not normalized:
        return None

    if ID_CARD_RE.search(normalized):
        return SensitiveMatch("id_card", "疑似身份证号")
    if _contains_bank_card(normalized):
        return SensitiveMatch("bank_card", "疑似银行卡号")
    if VERIFY_CODE_RE.search(normalized):
        return SensitiveMatch("verification_code", "疑似短信验证码")
    if PRIVATE_KEY_RE.search(normalized):
        return SensitiveMatch("private_key", "疑似私钥")
    if API_KEY_RE.search(normalized):
        return SensitiveMatch("api_key", "疑似 API key/token/secret")
    if _contains_password_like_text(normalized):
        return SensitiveMatch("password", "疑似密码或高敏凭证")
    return None


def _contains_password_like_text(text: str) -> bool:
    lower = text.lower()
    if not any(keyword in lower for keyword in PASSWORD_KEYWORDS):
        return False
    return bool(re.search(r"[:：=是]\s*\S{3,}", text) or re.search(r"\d{4,}", text))


def _contains_bank_card(text: str) -> bool:
    for match in BANK_CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 16 and _luhn_checksum_valid(digits):
            return True
    return False


def _luhn_checksum_valid(number: str) -> bool:
    total = 0
    reverse_digits = number[::-1]
    for index, char in enumerate(reverse_digits):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

