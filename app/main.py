from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.ai.intent import IntentParser, LLMIntentClient
from app.ai.llm import LLMClientConfig
from app.ai.summarize import LLMSummaryClient, SummaryService
from app.config import get_settings
from app.feishu.client import FeishuClient, FeishuClientError
from app.feishu.webhook import (
    challenge_response,
    is_challenge,
    parse_text_message,
    user_allowed,
    verify_event_token,
)
from app.logging_config import configure_logging
from app.scheduler.jobs import ReminderScheduler
from app.security.sensitive import SENSITIVE_REPLY, detect_sensitive
from app.services.export import LedgerExportService, handle_export_text
from app.services.knowledge import KnowledgeService, handle_knowledge_text
from app.services.ledger import LedgerService, handle_ledger_text
from app.services.obsidian_git import ObsidianGitSync
from app.services.todo import TodoContext, TodoService, handle_todo_text
from app.storage.db import Database
from app.storage.messages import MessageStore

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

db = Database(settings.database_path)
ledger_service = LedgerService(db)
todo_service = TodoService(db)
llm_config = LLMClientConfig(
    provider=settings.llm_provider,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
    responses_path=settings.llm_responses_path,
    timeout_seconds=settings.llm_timeout_seconds,
)
summary_service = SummaryService(
    LLMSummaryClient(config=llm_config)
)
obsidian_git_sync = (
    ObsidianGitSync(settings.obsidian_vault_path, push_enabled=settings.obsidian_git_push_enabled)
    if settings.obsidian_vault_path and settings.obsidian_git_sync_enabled
    else None
)
knowledge_service = KnowledgeService(db, settings.obsidian_vault_path, summary_service, git_sync=obsidian_git_sync)
export_service = LedgerExportService(db, settings.export_dir)
message_store = MessageStore(db)
feishu_client = FeishuClient(settings)
intent_parser = IntentParser(
    LLMIntentClient(config=llm_config)
)
reminder_scheduler = ReminderScheduler(
    todo_service=todo_service,
    send_text=feishu_client.send_text_to_open_id,
    interval_seconds=settings.reminder_scan_interval_seconds,
)

app = FastAPI(title="Personal Jarvis Bot", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    db.init()
    knowledge_service.init_vault()
    reminder_scheduler.start()
    logger.info("Jarvis bot started with database %s", settings.database_path)


@app.on_event("shutdown")
def on_shutdown() -> None:
    reminder_scheduler.stop()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()

    if "encrypt" in payload:
        raise HTTPException(
            status_code=501,
            detail="Encrypted Feishu callbacks are not enabled in MVP. Use verification token callbacks.",
        )

    if is_challenge(payload):
        try:
            return challenge_response(payload, settings)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        verify_event_token(payload, settings)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    message = parse_text_message(payload)
    if not message:
        logger.info("Ignored unsupported Feishu event")
        return {"status": "ignored"}

    if message.chat_type != "p2p":
        logger.info("Ignored non-private chat message %s", message.message_id)
        return {"status": "ignored"}

    if message.message_type != "text":
        _reply_safely(message.message_id, "我现在只支持文本消息。")
        return {"status": "ignored"}

    if not user_allowed(message, settings):
        logger.warning("Ignored message from non-whitelisted user: %s", message.user_id)
        return {"status": "ignored"}

    is_new = message_store.mark_processing(
        feishu_message_id=message.message_id,
        event_id=message.event_id,
    )
    if not is_new:
        logger.info("Ignored duplicate message %s", message.message_id)
        return {"status": "duplicate"}

    try:
        context = TodoContext(
            feishu_open_id=message.open_id,
            feishu_user_id=message.user_id,
        )
        reply = route_text(message.text, context=context)
        _reply_safely(message.message_id, reply)
        message_store.update_status(
            feishu_message_id=message.message_id,
            event_id=message.event_id,
            status="processed",
        )
    except Exception:
        logger.exception("Failed to process message %s", message.message_id)
        message_store.update_status(
            feishu_message_id=message.message_id,
            event_id=message.event_id,
            status="failed",
        )
        _reply_safely(message.message_id, "处理失败了，我已经记录日志，稍后可以排查。")
        raise

    return {"status": "ok"}


def route_text(text: str, *, context: TodoContext | None = None) -> str:
    normalized = text.strip()
    sensitive = detect_sensitive(normalized)
    if sensitive:
        logger.warning("Sensitive message blocked before AI: %s", sensitive.kind)
        return SENSITIVE_REPLY

    if normalized.lower() == "ping":
        return "pong"

    export_reply = handle_export_text(normalized, export_service)
    if export_reply:
        return export_reply

    knowledge_reply = handle_knowledge_text(normalized, knowledge_service)
    if knowledge_reply:
        return knowledge_reply

    todo_reply = handle_todo_text(normalized, todo_service, context=context)
    if todo_reply:
        return todo_reply

    ledger_reply = handle_ledger_text(normalized, ledger_service)
    if ledger_reply:
        return ledger_reply

    intent = intent_parser.parse(normalized)
    if intent.intent == "clarify" or intent.missing_fields:
        return intent.reply or f"我还需要这些信息：{', '.join(intent.missing_fields)}"
    if intent.intent == "knowledge.capture_text":
        knowledge_reply = handle_knowledge_text(
            f"整理进知识库：{intent.fields.get('content') or normalized}",
            knowledge_service,
        )
        if knowledge_reply:
            return knowledge_reply
    if intent.intent == "knowledge.capture_link":
        knowledge_reply = handle_knowledge_text(normalized, knowledge_service)
        if knowledge_reply:
            return knowledge_reply
    if intent.intent.startswith("todo."):
        todo_reply = handle_todo_text(normalized, todo_service, context=context)
        if todo_reply:
            return todo_reply
    if intent.intent.startswith("ledger."):
        ledger_reply = handle_ledger_text(normalized, ledger_service)
        if ledger_reply:
            return ledger_reply
    if intent.intent == "export.ledger_excel":
        export_reply = handle_export_text(normalized, export_service)
        if export_reply:
            return export_reply

    return "我还不能确定你想让我做什么。你可以说：记账、创建待办、设置提醒，或整理进知识库。"


def _reply_safely(message_id: str, text: str) -> None:
    try:
        feishu_client.reply_text(message_id, text)
    except FeishuClientError:
        logger.exception("Failed to reply Feishu message %s", message_id)
