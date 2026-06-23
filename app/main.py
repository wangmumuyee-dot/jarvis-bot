from __future__ import annotations

import base64
import binascii
import logging
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
from app.services.finance_p2 import FinanceP2Service, handle_finance_p2_text
from app.services.finance_web import FinanceEntryInput, FinanceWebService
from app.services.health import HealthService, handle_health_text
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
finance_p2_service = FinanceP2Service(
    db,
    export_service,
    settings.obsidian_vault_path,
    git_sync=obsidian_git_sync,
    summary_service=summary_service,
)
finance_web_service = FinanceWebService(db, ledger_service)
health_service = HealthService(db)
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
WEB_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
app.mount("/finance-static", StaticFiles(directory=WEB_STATIC_DIR), name="finance-static")


class FinanceCommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class FinanceEntryRequest(BaseModel):
    entry_type: str = Field(pattern="^(expense|income|refund|transfer|reimbursement)$")
    amount: float = Field(gt=0)
    currency: str = Field(default="CNY", pattern="^(CNY|USD|HKD|JPY|EUR)$")
    category: str = Field(default="其他", max_length=40)
    note: str = Field(default="", max_length=200)
    occurred_at: Optional[str] = None
    book: str = Field(default="日常账本", max_length=40)
    account: str = Field(default="默认账户", max_length=40)
    transfer_to_account: Optional[str] = Field(default=None, max_length=40)
    reimbursable: bool = False
    tags: List[str] = Field(default_factory=list, max_length=12)


class FinanceImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=1)


class FinanceAccountRequest(BaseModel):
    id: Optional[int] = None
    name: str = Field(min_length=1, max_length=40)
    account_type: str = Field(
        default="asset",
        pattern="^(asset|cash|debit_card|credit_card|wallet|liability|other)$",
    )
    currency: str = Field(default="CNY", pattern="^(CNY|USD|HKD|JPY|EUR)$")
    opening_balance: float = Field(default=0)


def _verify_finance_web_access(
    x_jarvis_web_token: Optional[str] = Header(default=None),
) -> None:
    if not settings.web_auth_token:
        return
    if x_jarvis_web_token != settings.web_auth_token:
        raise HTTPException(status_code=401, detail="Finance web token is required")


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


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/finance")


@app.get("/finance")
def finance_page() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "index.html")


@app.get("/finance-sw.js", include_in_schema=False)
def finance_service_worker() -> FileResponse:
    response = FileResponse(WEB_STATIC_DIR / "sw.js", media_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/api/finance/dashboard")
def finance_dashboard(_access: None = Depends(_verify_finance_web_access)) -> dict[str, Any]:
    return finance_web_service.dashboard()


@app.get("/api/health/bowel")
def health_bowel_month(
    year: Optional[int] = None,
    month: Optional[int] = None,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, Any]:
    today = date.today()
    try:
        return health_service.bowel_month_summary(year or today.year, month or today.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/finance/options")
def finance_options(_access: None = Depends(_verify_finance_web_access)) -> dict[str, Any]:
    return finance_web_service.options()


@app.get("/api/finance/entries")
def finance_entries(limit: int = 30, _access: None = Depends(_verify_finance_web_access)) -> dict[str, Any]:
    return {"entries": finance_web_service.entries(limit=limit)}


@app.post("/api/finance/entries")
def finance_create_entry(
    payload: FinanceEntryRequest,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, Any]:
    item = FinanceEntryInput(
        entry_type=payload.entry_type,  # type: ignore[arg-type]
        amount=payload.amount,
        currency=payload.currency,  # type: ignore[arg-type]
        category=payload.category,
        note=payload.note,
        occurred_at=payload.occurred_at,
        book=payload.book,
        account=payload.account,
        transfer_to_account=payload.transfer_to_account,
        reimbursable=payload.reimbursable,
        tags=tuple(payload.tags),
    )
    return finance_web_service.create_entry(item)


@app.put("/api/finance/entries/{entry_id}")
def finance_update_entry(
    entry_id: int,
    payload: FinanceEntryRequest,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, Any]:
    item = FinanceEntryInput(
        entry_type=payload.entry_type,  # type: ignore[arg-type]
        amount=payload.amount,
        currency=payload.currency,  # type: ignore[arg-type]
        category=payload.category,
        note=payload.note,
        occurred_at=payload.occurred_at,
        book=payload.book,
        account=payload.account,
        transfer_to_account=payload.transfer_to_account,
        reimbursable=payload.reimbursable,
        tags=tuple(payload.tags),
    )
    try:
        return finance_web_service.update_entry(entry_id, item)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/finance/entries/{entry_id}")
def finance_delete_entry(
    entry_id: int,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, str]:
    try:
        return finance_web_service.delete_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/finance/command")
def finance_command(
    payload: FinanceCommandRequest,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, str]:
    return {"reply": route_text(payload.text)}


@app.post("/api/finance/accounts")
def finance_upsert_account(
    payload: FinanceAccountRequest,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, Any]:
    try:
        return finance_web_service.upsert_account(
            account_id=payload.id,
            name=payload.name,
            account_type=payload.account_type,
            currency=payload.currency,
            opening_balance=payload.opening_balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/finance/accounts/{account_id}")
def finance_delete_account(
    account_id: int,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, str]:
    try:
        return finance_web_service.delete_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/finance/export")
def finance_export_file(
    scope: str = "month",
    redact: bool = False,
    _access: None = Depends(_verify_finance_web_access),
) -> FileResponse:
    if scope not in {"all", "month", "reimbursable"}:
        raise HTTPException(status_code=400, detail="Unsupported export scope")
    result = export_service.export(scope, redact_sensitive=redact)  # type: ignore[arg-type]
    return FileResponse(
        result.path,
        filename=result.path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/finance/import")
def finance_import_file(
    payload: FinanceImportRequest,
    _access: None = Depends(_verify_finance_web_access),
) -> dict[str, str]:
    filename = _safe_xlsx_filename(payload.filename)
    import_dir = export_service.export_dir / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    path = _unique_upload_path(import_dir / filename)
    try:
        content = payload.content_base64.split(",", 1)[-1]
        path.write_bytes(base64.b64decode(content, validate=True))
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 file content") from exc

    reply = route_text("自动导入账单")
    return {"reply": reply}


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

    health_reply = handle_health_text(normalized, health_service)
    if health_reply:
        return health_reply

    template = finance_p2_service.expand_quick_template(normalized)
    if template:
        if template.command_text.strip() == normalized:
            return f"模板 {template.name} 指向了自己，已停止执行，避免循环。"
        executed = route_text(template.command_text, context=context)
        return f"已使用模板「{template.name}」：{template.command_text}\n{executed}"

    finance_p2_reply = handle_finance_p2_text(normalized, finance_p2_service)
    if finance_p2_reply:
        return finance_p2_reply

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


def _safe_xlsx_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    safe = "".join(char if char.isalnum() or char in {"-", "_", ".", " "} else "_" for char in name)
    return safe or "ledger-import.xlsx"


def _unique_upload_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=500, detail="Unable to allocate upload filename")


def _reply_safely(message_id: str, text: str) -> None:
    try:
        feishu_client.reply_text(message_id, text)
    except FeishuClientError:
        logger.exception("Failed to reply Feishu message %s", message_id)
