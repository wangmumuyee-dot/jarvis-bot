from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from app.ai.llm import LLMClientConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryResult:
    title: str
    summary: str
    key_points: list[str]
    action_items: list[str]
    tags: list[str]
    related: list[str]


class LLMSummaryError(RuntimeError):
    pass


class LLMSummaryClient:
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

    def summarize(self, *, title: str, content: str, source_url: str | None = None) -> SummaryResult:
        if not self.config.api_key and not self.transport:
            raise LLMSummaryError("LLM_API_KEY is not configured")
        body = {
            "model": self.config.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "你是个人知识库助手。请把网页或文本整理为中文知识笔记摘要，"
                        "输出严格 JSON，包含 title、summary、key_points、action_items、tags、related。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"标题：{title}\n来源：{source_url or ''}\n正文：\n{content[:12000]}",
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "summary_result",
                    "strict": True,
                    "schema": SUMMARY_JSON_SCHEMA,
                }
            },
        }
        response = self.transport(body) if self.transport else self._post(body)
        output_text = _extract_output_text(response)
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LLMSummaryError(f"LLM provider returned invalid summary JSON: {output_text[:200]}") from exc
        return summary_from_dict(data)

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
            raise LLMSummaryError(f"LLM summary request failed: {exc}") from exc


class SummaryService:
    def __init__(self, client: LLMSummaryClient) -> None:
        self.client = client

    def summarize(self, *, title: str, content: str, source_url: str | None = None) -> SummaryResult:
        if self.client.configured():
            try:
                return self.client.summarize(title=title, content=content, source_url=source_url)
            except LLMSummaryError:
                logger.exception("LLM summary failed; falling back to local summary")
        return summarize_locally(title=title, content=content, source_url=source_url)


SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "summary", "key_points", "action_items", "tags", "related"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "action_items": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "related": {"type": "array", "items": {"type": "string"}},
    },
}


def summarize_locally(*, title: str, content: str, source_url: str | None = None) -> SummaryResult:
    sentences = [item.strip(" 。；;\n") for item in content.replace("\r", "\n").split("\n") if item.strip()]
    if len(sentences) < 3:
        sentences = [item.strip(" 。；;") for item in content.replace("。", "\n").split("\n") if item.strip()]
    key_points = sentences[:5] or [content[:120]]
    summary = "；".join(key_points[:2])[:240]
    action_items = [item for item in key_points if any(token in item.lower() for token in ["可以", "应该", "需要", "todo", "下一步"])][:3]
    tags = _tags_for_content(f"{title}\n{content}\n{source_url or ''}")
    related = ["个人机器人"] if "个人机器人" in content or "jarvis" in content.lower() else []
    return SummaryResult(
        title=title[:80] or "链接笔记",
        summary=summary,
        key_points=key_points,
        action_items=action_items,
        tags=tags,
        related=related,
    )


def summary_from_dict(data: dict[str, Any]) -> SummaryResult:
    return SummaryResult(
        title=str(data.get("title") or "链接笔记"),
        summary=str(data.get("summary") or ""),
        key_points=[str(item) for item in data.get("key_points") or []],
        action_items=[str(item) for item in data.get("action_items") or []],
        tags=[str(item) for item in data.get("tags") or []],
        related=[str(item) for item in data.get("related") or []],
    )


def _extract_output_text(response: dict[str, Any]) -> str:
    if "output_text" in response:
        return str(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and "text" in content:
                return str(content["text"])
    raise LLMSummaryError(f"Unable to find output text in LLM response: {response}")


OpenAISummaryError = LLMSummaryError
OpenAISummaryClient = LLMSummaryClient


def _tags_for_content(text: str) -> list[str]:
    lower = text.lower()
    tags: list[str] = []
    if any(token in lower for token in ["ai", "agent", "openai", "大模型", "人工智能"]):
        tags.append("AI")
    if "个人机器人" in text or "jarvis" in lower or "飞书" in text:
        tags.append("个人机器人")
    if any(token in text for token in ["财务", "记账", "报销", "消费"]):
        tags.append("财务")
    return tags or ["文章"]
