from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.storage.db import Database

EntryType = Literal["expense", "income", "refund", "transfer", "reimbursement"]


@dataclass(frozen=True)
class LedgerEntryDraft:
    entry_type: EntryType
    amount: float
    currency: str
    category: str
    note: str
    occurred_at: datetime
    reimbursable: bool
    reimbursement_status: Literal["none", "pending", "received"]
    source_text: str


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    draft: LedgerEntryDraft


@dataclass(frozen=True)
class LedgerQueryResult:
    total: float
    count: int
    title: str


class LedgerParseError(ValueError):
    pass


AMOUNT_RE = re.compile(r"(?<!\d)(\d+(?:\.\d{1,2})?)(?!\d)")

CATEGORY_KEYWORDS = [
    ("餐饮", ["午饭", "晚饭", "早饭", "早餐", "午餐", "晚餐", "吃饭", "咖啡", "奶茶", "餐"]),
    ("交通", ["打车", "地铁", "公交", "高铁", "火车", "机票", "出租", "停车"]),
    ("购物", ["买", "购物", "衣服", "鞋", "日用品"]),
    ("学习", ["书", "课程", "学习", "资料"]),
    ("健康", ["药", "医院", "体检", "健身"]),
    ("居住", ["房租", "水电", "物业", "宽带"]),
    ("娱乐", ["电影", "游戏", "演出", "会员"]),
]


def parse_ledger_text(text: str, now: datetime | None = None) -> LedgerEntryDraft | None:
    stripped = text.strip()
    if not stripped:
        return None

    if _looks_like_query(stripped):
        return None

    match = AMOUNT_RE.search(stripped)
    if not match:
        return None

    amount = float(match.group(1))
    now = now or datetime.now()
    entry_type = _detect_entry_type(stripped)
    reimbursable = "待报销" in stripped
    reimbursement_status: Literal["none", "pending", "received"] = "none"
    if reimbursable:
        reimbursement_status = "pending"
    if entry_type == "reimbursement":
        reimbursement_status = "received"

    category = _detect_category(stripped, entry_type)
    note = _clean_note(stripped, match.group(0))

    return LedgerEntryDraft(
        entry_type=entry_type,
        amount=amount,
        currency="CNY",
        category=category,
        note=note or category,
        occurred_at=_detect_date(stripped, now),
        reimbursable=reimbursable,
        reimbursement_status=reimbursement_status,
        source_text=stripped,
    )


class LedgerService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, draft: LedgerEntryDraft) -> LedgerEntry:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ledger_entries (
                    entry_type, amount, currency, category, note, occurred_at,
                    reimbursable, reimbursement_status, source_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.entry_type,
                    draft.amount,
                    draft.currency,
                    draft.category,
                    draft.note,
                    draft.occurred_at.isoformat(timespec="seconds"),
                    1 if draft.reimbursable else 0,
                    draft.reimbursement_status,
                    draft.source_text,
                ),
            )
            entry_id = int(cursor.lastrowid)
        return LedgerEntry(id=entry_id, draft=draft)

    def query(self, text: str, now: datetime | None = None) -> LedgerQueryResult | None:
        now = now or datetime.now()
        stripped = text.strip()
        if not _looks_like_query(stripped):
            return None
        if "待报销" in stripped:
            return self._sum_reimbursable()
        if "今天" in stripped:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            category = _category_from_query(stripped)
            return self._sum_between(start, end, category, "今天")
        if "这个月" in stripped or "本月" in stripped:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
            category = _category_from_query(stripped)
            title = f"本月{category or ''}流水"
            return self._sum_between(start, end, category, title)
        return None

    def _sum_between(
        self,
        start: datetime,
        end: datetime,
        category: str | None,
        title: str,
    ) -> LedgerQueryResult:
        where = "occurred_at >= ? AND occurred_at < ?"
        params: list[object] = [start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")]
        if category:
            where += " AND category = ?"
            params.append(category)

        with self.db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
                FROM ledger_entries
                WHERE {where}
                """,
                params,
            ).fetchone()
        return LedgerQueryResult(total=float(row["total"]), count=int(row["count"]), title=title)

    def _sum_reimbursable(self) -> LedgerQueryResult:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
                FROM ledger_entries
                WHERE reimbursable = 1 AND reimbursement_status = 'pending'
                """
            ).fetchone()
        return LedgerQueryResult(total=float(row["total"]), count=int(row["count"]), title="待报销流水")


def handle_ledger_text(text: str, service: LedgerService) -> str | None:
    query = service.query(text)
    if query:
        return f"{query.title}共 {query.total:.2f} 元，{query.count} 条记录。"

    draft = parse_ledger_text(text)
    if not draft:
        return None

    entry = service.create(draft)
    status = ""
    if draft.reimbursable:
        status = "，报销状态：待报销"
    if draft.reimbursement_status == "received":
        status = "，报销状态：已到账"
    return (
        f"已记录流水 #{entry.id}：{draft.amount:.2f} 元，"
        f"类型：{_type_label(draft.entry_type)}，分类：{draft.category}，"
        f"备注：{draft.note}{status}。"
    )


def _looks_like_query(text: str) -> bool:
    return any(word in text for word in ["多少", "查询", "统计", "有哪些", "花了多少钱"])


def _detect_entry_type(text: str) -> EntryType:
    if "报销到账" in text or "报销到帐" in text:
        return "reimbursement"
    if "退款" in text or "退回" in text:
        return "refund"
    if "转账" in text or "转给" in text:
        return "transfer"
    if "工资" in text or "收入" in text or "到账" in text:
        return "income"
    return "expense"


def _detect_category(text: str, entry_type: EntryType) -> str:
    if entry_type == "income":
        return "收入"
    if entry_type == "refund":
        return "退款"
    if entry_type == "transfer":
        return "转账"
    if entry_type == "reimbursement":
        return "报销"
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return "其他"


def _category_from_query(text: str) -> str | None:
    for category, keywords in CATEGORY_KEYWORDS:
        if category in text or any(keyword in text for keyword in keywords):
            return category
    for category in ["收入", "退款", "转账", "报销", "其他"]:
        if category in text:
            return category
    return None


def _detect_date(text: str, now: datetime) -> datetime:
    if "昨天" in text:
        return now - timedelta(days=1)
    if "前天" in text:
        return now - timedelta(days=2)
    return now


def _clean_note(text: str, amount_text: str) -> str:
    note = text.replace(amount_text, " ")
    for token in ["今天", "昨天", "前天", "花了", "花", "元", "块钱", "块", "待报销"]:
        note = note.replace(token, " ")
    return " ".join(note.split())


def _type_label(entry_type: EntryType) -> str:
    return {
        "expense": "支出",
        "income": "收入",
        "refund": "退款",
        "transfer": "转账",
        "reimbursement": "报销",
    }[entry_type]
