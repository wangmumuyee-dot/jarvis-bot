from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class FeishuClientError(RuntimeError):
    pass


@dataclass
class _TokenCache:
    token: str = ""
    expires_at: float = 0.0


class FeishuClient:
    API_BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tenant_token = _TokenCache()

    def reply_text(self, message_id: str, text: str) -> None:
        if not self.settings.feishu_configured:
            logger.info("Feishu is not configured; reply skipped: %s", text)
            return

        self._request_json(
            "POST",
            f"{self.API_BASE}/im/v1/messages/{message_id}/reply",
            body={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            auth=True,
        )

    def send_text_to_open_id(self, open_id: str, text: str) -> None:
        if not self.settings.feishu_configured:
            logger.info("Feishu is not configured; proactive message skipped: %s", text)
            return

        self._request_json(
            "POST",
            f"{self.API_BASE}/im/v1/messages?receive_id_type=open_id",
            body={
                "receive_id": open_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            auth=True,
        )

    def _tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_token.token and self._tenant_token.expires_at > now + 60:
            return self._tenant_token.token

        data = self._request_json(
            "POST",
            f"{self.API_BASE}/auth/v3/tenant_access_token/internal",
            body={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
            auth=False,
        )
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuClientError(f"tenant_access_token missing: {data}")
        expire = float(data.get("expire", 7200))
        self._tenant_token = _TokenCache(token=token, expires_at=now + expire)
        return token

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any],
        auth: bool,
    ) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self._tenant_access_token()}"

        request = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise FeishuClientError(f"Feishu request failed: {exc}") from exc

        data = json.loads(raw)
        if data.get("code", 0) != 0:
            raise FeishuClientError(f"Feishu API error: {data}")
        return data
