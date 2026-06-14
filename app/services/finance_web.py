from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Literal

from app.services.ledger import EntryType, LedgerEntryDraft, LedgerService, _type_label
from app.storage.db import Database

Currency = Literal["CNY", "USD", "HKD", "JPY", "EUR"]


@dataclass(frozen=True)
class FinanceEntryInput:
    entry_type: EntryType
    amount: float
    currency: Currency
    category: str
    note: str
    occurred_at: str | None = None
    book: str = "日常账本"
    account: str = "默认账户"
    transfer_to_account: str | None = None
    reimbursable: bool = False
    tags: tuple[str, ...] = ()


class FinanceWebService:
    def __init__(self, db: Database, ledger_service: LedgerService) -> None:
        self.db = db
        self.ledger_service = ledger_service

    def dashboard(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        start_text = start.isoformat(timespec="seconds")
        end_text = end.isoformat(timespec="seconds")

        with self.db.connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN entry_type = 'expense' AND currency = 'CNY' THEN amount ELSE 0 END), 0) AS expense,
                    COALESCE(SUM(CASE WHEN entry_type IN ('income', 'refund', 'reimbursement') AND currency = 'CNY' THEN amount ELSE 0 END), 0) AS income,
                    COUNT(*) AS count
                FROM ledger_entries
                WHERE occurred_at >= ? AND occurred_at < ?
                """,
                (start_text, end_text),
            ).fetchone()
            pending = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
                FROM ledger_entries
                WHERE reimbursable = 1 AND reimbursement_status = 'pending'
                """
            ).fetchone()
            category_rows = conn.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
                FROM ledger_entries
                WHERE entry_type = 'expense'
                    AND currency = 'CNY'
                    AND occurred_at >= ?
                    AND occurred_at < ?
                GROUP BY category
                ORDER BY total DESC
                LIMIT 8
                """,
                (start_text, end_text),
            ).fetchall()
            budget_rows = conn.execute(
                """
                SELECT
                    budgets.category,
                    budgets.amount,
                    budgets.currency,
                    COALESCE(SUM(ledger_entries.amount), 0) AS spent
                FROM budgets
                LEFT JOIN ledger_entries ON ledger_entries.category = budgets.category
                    AND ledger_entries.entry_type = 'expense'
                    AND ledger_entries.currency = budgets.currency
                    AND ledger_entries.occurred_at >= ?
                    AND ledger_entries.occurred_at < ?
                WHERE budgets.period = 'monthly'
                GROUP BY budgets.id
                ORDER BY spent / budgets.amount DESC, budgets.updated_at DESC
                LIMIT 8
                """,
                (start_text, end_text),
            ).fetchall()
            saving_rows = conn.execute(
                """
                SELECT name, target_amount, current_amount, currency, status
                FROM saving_goals
                ORDER BY status = 'completed', updated_at DESC
                LIMIT 6
                """
            ).fetchall()
            debt_rows = conn.execute(
                """
                SELECT debt_type, person, amount, repaid_amount, currency
                FROM ledger_debts
                WHERE status = 'open' AND amount > repaid_amount
                ORDER BY updated_at DESC, id DESC
                LIMIT 8
                """
            ).fetchall()

        expense = float(totals["expense"])
        income = float(totals["income"])
        return {
            "period": now.strftime("%Y-%m"),
            "totals": {
                "expense": expense,
                "income": income,
                "net": income - expense,
                "count": int(totals["count"]),
                "pending_reimbursement": float(pending["total"]),
                "pending_reimbursement_count": int(pending["count"]),
            },
            "categories": [
                {
                    "category": row["category"],
                    "total": float(row["total"]),
                    "count": int(row["count"]),
                    "share": 0 if expense <= 0 else round(float(row["total"]) / expense * 100, 1),
                }
                for row in category_rows
            ],
            "budgets": [
                {
                    "category": row["category"],
                    "amount": float(row["amount"]),
                    "spent": float(row["spent"]),
                    "remaining": float(row["amount"]) - float(row["spent"]),
                    "currency": row["currency"],
                    "progress": _progress(float(row["spent"]), float(row["amount"])),
                }
                for row in budget_rows
            ],
            "saving_goals": [
                {
                    "name": row["name"],
                    "target_amount": float(row["target_amount"]),
                    "current_amount": float(row["current_amount"]),
                    "currency": row["currency"],
                    "status": row["status"],
                    "progress": _progress(float(row["current_amount"]), float(row["target_amount"])),
                }
                for row in saving_rows
            ],
            "debts": [
                {
                    "debt_type": row["debt_type"],
                    "person": row["person"],
                    "remaining": float(row["amount"]) - float(row["repaid_amount"]),
                    "currency": row["currency"],
                }
                for row in debt_rows
            ],
        }

    def options(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            category_rows = conn.execute(
                """
                SELECT name, parent_name, entry_type
                FROM ledger_categories
                WHERE status = 'active'
                ORDER BY parent_name IS NOT NULL, parent_name, name
                """
            ).fetchall()
            account_rows = conn.execute(
                """
                SELECT name, account_type, currency
                FROM ledger_accounts
                WHERE status = 'active'
                ORDER BY updated_at DESC, name
                """
            ).fetchall()
            book_rows = conn.execute(
                """
                SELECT name
                FROM ledger_books
                WHERE status = 'active'
                ORDER BY updated_at DESC, name
                """
            ).fetchall()
            template_rows = conn.execute(
                """
                SELECT name, command_text, usage_count
                FROM quick_templates
                ORDER BY usage_count DESC, updated_at DESC
                LIMIT 12
                """
            ).fetchall()

        return {
            "entry_types": [
                {"value": "expense", "label": "支出"},
                {"value": "income", "label": "收入"},
                {"value": "refund", "label": "退款"},
                {"value": "transfer", "label": "转账"},
                {"value": "reimbursement", "label": "报销"},
            ],
            "currencies": ["CNY", "USD", "HKD", "JPY", "EUR"],
            "categories": [
                {
                    "name": row["name"],
                    "parent_name": row["parent_name"],
                    "entry_type": row["entry_type"],
                    "label": f"{row['parent_name']}/{row['name']}" if row["parent_name"] else row["name"],
                }
                for row in category_rows
            ],
            "accounts": [dict(row) for row in account_rows],
            "books": [row["name"] for row in book_rows],
            "templates": [dict(row) for row in template_rows],
        }

    def entries(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ledger_entries.id,
                    ledger_entries.entry_type,
                    ledger_entries.amount,
                    ledger_entries.currency,
                    ledger_entries.category,
                    ledger_entries.note,
                    ledger_entries.occurred_at,
                    ledger_entries.reimbursable,
                    ledger_entries.reimbursement_status,
                    COALESCE(ledger_books.name, '日常账本') AS book,
                    COALESCE(ledger_accounts.name, '默认账户') AS account,
                    COALESCE(target_accounts.name, '') AS transfer_to_account,
                    GROUP_CONCAT(ledger_tags.name, ',') AS tags
                FROM ledger_entries
                LEFT JOIN ledger_books ON ledger_books.id = ledger_entries.book_id
                LEFT JOIN ledger_accounts ON ledger_accounts.id = ledger_entries.account_id
                LEFT JOIN ledger_accounts AS target_accounts ON target_accounts.id = ledger_entries.transfer_to_account_id
                LEFT JOIN ledger_entry_tags ON ledger_entry_tags.entry_id = ledger_entries.id
                LEFT JOIN ledger_tags ON ledger_tags.id = ledger_entry_tags.tag_id
                GROUP BY ledger_entries.id
                ORDER BY ledger_entries.occurred_at DESC, ledger_entries.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "entry_type": row["entry_type"],
                "entry_type_label": _type_label(row["entry_type"]),
                "amount": float(row["amount"]),
                "currency": row["currency"],
                "category": row["category"],
                "note": row["note"],
                "occurred_at": row["occurred_at"],
                "reimbursable": bool(row["reimbursable"]),
                "reimbursement_status": row["reimbursement_status"],
                "book": row["book"],
                "account": row["account"],
                "transfer_to_account": row["transfer_to_account"],
                "tags": [tag for tag in str(row["tags"] or "").split(",") if tag],
            }
            for row in rows
        ]

    def create_entry(self, item: FinanceEntryInput) -> dict[str, Any]:
        occurred_at = _parse_occurred_at(item.occurred_at)
        reimbursement_status = "pending" if item.reimbursable else "none"
        if item.entry_type == "reimbursement":
            reimbursement_status = "received"
        draft = LedgerEntryDraft(
            entry_type=item.entry_type,
            amount=item.amount,
            currency=item.currency,
            category=item.category.strip() or "其他",
            subcategory=None,
            note=item.note.strip() or item.category.strip() or "未命名流水",
            occurred_at=occurred_at,
            reimbursable=item.reimbursable,
            reimbursement_status=reimbursement_status,
            source_text=_source_text(item, occurred_at),
            book=item.book.strip() or "日常账本",
            account=item.account.strip() or "默认账户",
            transfer_to_account=item.transfer_to_account.strip() if item.transfer_to_account else None,
            tags=tuple(tag.strip("# ") for tag in item.tags if tag.strip("# ")),
        )
        entry = self.ledger_service.create(draft)
        warning = self.ledger_service.budget_warning_for_entry(draft)
        return {
            "id": entry.id,
            "reply": _entry_reply(entry.id, draft, warning),
            "entry": {
                "id": entry.id,
                "entry_type": draft.entry_type,
                "entry_type_label": _type_label(draft.entry_type),
                "amount": draft.amount,
                "currency": draft.currency,
                "category": draft.category,
                "note": draft.note,
                "occurred_at": draft.occurred_at.isoformat(timespec="seconds"),
                "book": draft.book,
                "account": draft.account,
                "tags": list(draft.tags),
            },
        }


def _parse_occurred_at(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    cleaned = value.strip()
    if not cleaned:
        return datetime.now()
    if "T" in cleaned:
        return datetime.fromisoformat(cleaned)
    return datetime.combine(datetime.fromisoformat(cleaned).date(), time(hour=12))


def _progress(current: float, target: float) -> float:
    if target <= 0:
        return 0
    return round(max(0, current) / target * 100, 1)


def _source_text(item: FinanceEntryInput, occurred_at: datetime) -> str:
    tags = " ".join(f"#{tag.strip('# ')}" for tag in item.tags if tag.strip("# "))
    parts = [
        "网页记账",
        occurred_at.strftime("%Y-%m-%d"),
        item.note.strip(),
        f"{item.amount:.2f}",
        item.currency,
        f"分类{item.category.strip()}",
        f"用{item.account.strip()}" if item.account.strip() else "",
        f"记到{item.book.strip()}" if item.book.strip() else "",
        tags,
    ]
    return " ".join(part for part in parts if part)


def _entry_reply(entry_id: int, draft: LedgerEntryDraft, warning: str | None) -> str:
    tags = f"，标签：{'、'.join('#' + tag for tag in draft.tags)}" if draft.tags else ""
    transfer = f"，转入：{draft.transfer_to_account}" if draft.transfer_to_account else ""
    warning_text = f"\n{warning}" if warning else ""
    return (
        f"已记录流水 #{entry_id}：{draft.amount:.2f} {draft.currency}，"
        f"类型：{_type_label(draft.entry_type)}，分类：{draft.category}，"
        f"账户：{draft.account}{transfer}，备注：{draft.note}{tags}。{warning_text}"
    )

