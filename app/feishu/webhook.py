from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass(frozen=True)
class FeishuTextMessage:
    event_id: str | None
    message_id: str
    chat_type: str
    message_type: str
    text: str
    user_id: str | None
    open_id: str | None


def is_challenge(payload: dict[str, Any]) -> bool:
    return "challenge" in payload


def challenge_response(payload: dict[str, Any], settings: Settings) -> dict[str, str]:
    token = payload.get("token")
    if settings.feishu_verification_token and token:
        if token != settings.feishu_verification_token:
            raise ValueError("Invalid Feishu verification token")
    return {"challenge": str(payload["challenge"])}


def verify_event_token(payload: dict[str, Any], settings: Settings) -> None:
    if not settings.feishu_verification_token:
        return

    token = payload.get("token") or payload.get("header", {}).get("token")
    if token and token != settings.feishu_verification_token:
        raise ValueError("Invalid Feishu event token")


def parse_text_message(payload: dict[str, Any]) -> FeishuTextMessage | None:
    header = payload.get("header") or {}
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}

    message_id = message.get("message_id")
    if not message_id:
        return None

    content = message.get("content") or "{}"
    try:
        content_data = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        content_data = {}

    return FeishuTextMessage(
        event_id=header.get("event_id"),
        message_id=message_id,
        chat_type=message.get("chat_type", ""),
        message_type=message.get("message_type", ""),
        text=str(content_data.get("text", "")).strip(),
        user_id=sender_id.get("user_id"),
        open_id=sender_id.get("open_id"),
    )


def user_allowed(message: FeishuTextMessage, settings: Settings) -> bool:
    if not settings.allowed_feishu_user_ids:
        return True
    return bool(
        (message.user_id and message.user_id in settings.allowed_feishu_user_ids)
        or (message.open_id and message.open_id in settings.allowed_feishu_user_ids)
    )
