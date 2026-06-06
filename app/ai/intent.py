from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from app.ai.llm import LLMClientConfig
from app.ai.prompts import INTENT_SYSTEM_PROMPT
from app.ai.schema import INTENT_JSON_SCHEMA

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    confidence: float
    fields: dict[str, object]
    missing_fields: list[str]
    reply: str


class LLMIntentError(RuntimeError):
    pass


class LLMIntentClient:
    def __init__(
        self,
        *,
        config: LLMClientConfig,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    def configured(self) -> bool:
        return self.config.configured()

    def parse(self, text: str) -> IntentResult:
        if not self.config.api_key and not self.transport:
            raise LLMIntentError("LLM_API_KEY is not configured")

        body = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "intent_result",
                    "strict": True,
                    "schema": INTENT_JSON_SCHEMA,
                }
            },
        }
        response = self.transport(body) if self.transport else self._post(body)
        output_text = _extract_output_text(response)
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LLMIntentError(f"LLM provider returned invalid JSON: {output_text[:200]}") from exc
        return intent_from_dict(data)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.config.responses_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMIntentError(f"LLM request failed: {exc}") from exc


class IntentParser:
    def __init__(self, client: LLMIntentClient) -> None:
        self.client = client

    def parse(self, text: str) -> IntentResult:
        if self.client.configured():
            try:
                return self.client.parse(text)
            except LLMIntentError:
                logger.exception("LLM intent parsing failed; falling back to local classifier")
        return classify_intent_locally(text)


def classify_intent_locally(text: str) -> IntentResult:
    stripped = text.strip()
    lower = stripped.lower()
    url = _find_url(stripped)

    if not stripped:
        return _result("unknown", 0.0, reply="我没有收到有效内容。")

    if url and any(token in stripped for token in ["总结", "整理", "知识库", "笔记"]):
        return _result(
            "knowledge.capture_link",
            0.92,
            fields={"source_url": url, "content": stripped},
            reply="我会整理这个链接。",
        )

    if any(token in stripped for token in ["总结这段话", "整理进知识库", "放进知识库", "写入知识库", "沉淀成笔记"]):
        return _result(
            "knowledge.capture_text",
            0.9,
            fields={"content": stripped},
            reply="我会整理这段内容。",
        )

    if any(stripped.startswith(prefix) for prefix in ["完成", "做完", "已完成"]):
        return _result("todo.complete", 0.9, fields={"todo_title": stripped}, reply="我会完成这个待办。")

    if "待办" in stripped and any(token in stripped for token in ["哪些", "查询", "看看", "有什么", "今天", "全部", "未完成"]):
        return _result("todo.query", 0.88, reply="我会查询待办。")

    if any(stripped.startswith(prefix) for prefix in ["记一下", "记下", "待办"]) or "提醒我" in stripped:
        missing = [] if _has_todo_title(stripped) else ["todo_title"]
        intent = "todo.create" if not missing else "clarify"
        reply = "我会创建待办。" if not missing else "你想让我提醒什么？请补充待办内容。"
        return _result(intent, 0.86, missing_fields=missing, fields={"todo_title": stripped}, reply=reply)

    if any(token in stripped for token in ["导出", "excel", "Excel", "账单"]):
        return _result("export.ledger_excel", 0.82, reply="我会导出账本。")

    if _looks_like_ledger_query(stripped):
        return _result("ledger.query", 0.86, reply="我会查询账本。")

    if _looks_like_ledger_create(stripped):
        amount = _extract_amount(stripped)
        missing = [] if amount is not None else ["amount"]
        intent = "ledger.create" if amount is not None else "clarify"
        reply = "我会记录账本流水。" if not missing else "你想记录多少钱？请补充金额。"
        return _result("ledger.create" if amount is not None else intent, 0.84, fields={"amount": amount}, missing_fields=missing, reply=reply)

    if lower in {"ping", "pong"}:
        return _result("unknown", 0.3, reply="这是调试消息。")

    return _result("unknown", 0.2, reply="我还不能确定你想让我做什么。")


def intent_from_dict(data: dict[str, Any]) -> IntentResult:
    return IntentResult(
        intent=str(data.get("intent", "unknown")),
        confidence=float(data.get("confidence", 0)),
        fields=dict(data.get("fields") or {}),
        missing_fields=[str(item) for item in data.get("missing_fields") or []],
        reply=str(data.get("reply", "")),
    )


def _result(
    intent: str,
    confidence: float,
    *,
    fields: dict[str, object] | None = None,
    missing_fields: list[str] | None = None,
    reply: str,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=confidence,
        fields=fields or {},
        missing_fields=missing_fields or [],
        reply=reply,
    )


def _extract_output_text(response: dict[str, Any]) -> str:
    if "output_text" in response:
        return str(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and "text" in content:
                return str(content["text"])
    raise LLMIntentError(f"Unable to find output text in LLM response: {response}")


OpenAIIntentError = LLMIntentError
OpenAIIntentClient = LLMIntentClient


def _find_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip("，。,.") if match else None


def _extract_amount(text: str) -> float | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d{1,2})?)(?!\d)", text)
    return float(match.group(1)) if match else None


def _looks_like_ledger_query(text: str) -> bool:
    return any(token in text for token in ["多少", "查询", "统计", "有哪些", "花了多少钱", "待报销"]) and any(
        token in text for token in ["钱", "餐饮", "收入", "支出", "报销", "账", "花"]
    )


def _looks_like_ledger_create(text: str) -> bool:
    if _extract_amount(text) is None:
        return False
    keywords = ["花", "午饭", "晚饭", "打车", "买", "工资", "退款", "转账", "报销", "收入", "餐", "书"]
    return any(keyword in text for keyword in keywords)


def _has_todo_title(text: str) -> bool:
    cleaned = text
    for token in ["提醒我", "记一下", "记下", "待办", "今天", "明天", "后天"]:
        cleaned = cleaned.replace(token, " ")
    return bool(cleaned.strip(" ：:，,。"))
