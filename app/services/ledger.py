from __future__ import annotations

import re
import calendar
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
    subcategory: str | None
    note: str
    occurred_at: datetime
    reimbursable: bool
    reimbursement_status: Literal["none", "pending", "received"]
    source_text: str
    book: str = "日常账本"
    account: str = "默认账户"
    transfer_to_account: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    draft: LedgerEntryDraft


@dataclass(frozen=True)
class LedgerQueryResult:
    total: float
    count: int
    title: str


@dataclass(frozen=True)
class LedgerSearchItem:
    id: int
    amount: float
    category: str
    note: str
    occurred_at: str


@dataclass(frozen=True)
class LedgerBudgetResult:
    category: str
    amount: float
    spent: float
    remaining: float
    period: str


@dataclass(frozen=True)
class AccountBalanceResult:
    account: str
    balance: float
    currency: str


@dataclass(frozen=True)
class RecurringGenerationResult:
    generated_count: int
    entry_ids: tuple[int, ...]


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

    category, subcategory = _detect_category_detail(stripped, entry_type)
    note = _clean_note(stripped, match.group(0))
    book = _extract_book(stripped)
    account = _extract_account(stripped, entry_type)
    transfer_to_account = _extract_transfer_to_account(stripped) if entry_type == "transfer" else None
    tags = tuple(_extract_tags(stripped))

    return LedgerEntryDraft(
        entry_type=entry_type,
        amount=amount,
        currency="CNY",
        category=category,
        subcategory=subcategory,
        note=note or category,
        occurred_at=_detect_date(stripped, now),
        reimbursable=reimbursable,
        reimbursement_status=reimbursement_status,
        source_text=stripped,
        book=book,
        account=account,
        transfer_to_account=transfer_to_account,
        tags=tags,
    )


class LedgerService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, draft: LedgerEntryDraft) -> LedgerEntry:
        with self.db.connect() as conn:
            book_id = self._ensure_book(conn, draft.book)
            account_id = self._ensure_account(conn, draft.account)
            transfer_to_account_id = (
                self._ensure_account(conn, draft.transfer_to_account) if draft.transfer_to_account else None
            )
            category_id = self._ensure_category(conn, draft.category, draft.subcategory, draft.entry_type)
            cursor = conn.execute(
                """
                INSERT INTO ledger_entries (
                    book_id, account_id, category_id, transfer_to_account_id,
                    entry_type, amount, currency, category, note, occurred_at,
                    reimbursable, reimbursement_status, source_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id,
                    account_id,
                    category_id,
                    transfer_to_account_id,
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
            for tag in draft.tags:
                tag_id = self._ensure_tag(conn, tag)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ledger_entry_tags (entry_id, tag_id)
                    VALUES (?, ?)
                    """,
                    (entry_id, tag_id),
                )
        return LedgerEntry(id=entry_id, draft=draft)

    def _ensure_book(self, conn, name: str) -> int:
        conn.execute("INSERT OR IGNORE INTO ledger_books (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM ledger_books WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def _ensure_account(self, conn, name: str) -> int:
        account_type = _infer_account_type(name)
        conn.execute(
            """
            INSERT OR IGNORE INTO ledger_accounts (name, account_type)
            VALUES (?, ?)
            """,
            (name, account_type),
        )
        row = conn.execute("SELECT id FROM ledger_accounts WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def _ensure_category(self, conn, category: str, subcategory: str | None, entry_type: EntryType) -> int:
        name = subcategory or category
        parent_name = category if subcategory else None
        conn.execute(
            """
            INSERT OR IGNORE INTO ledger_categories (name, parent_name, entry_type)
            VALUES (?, ?, ?)
            """,
            (name, parent_name, entry_type),
        )
        row = conn.execute(
            """
            SELECT id FROM ledger_categories
            WHERE name = ? AND parent_name IS ? AND entry_type = ?
            """,
            (name, parent_name, entry_type),
        ).fetchone()
        return int(row["id"])

    def _ensure_tag(self, conn, name: str) -> int:
        conn.execute("INSERT OR IGNORE INTO ledger_tags (name) VALUES (?)", (name,))
        row = conn.execute("SELECT id FROM ledger_tags WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

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

    def set_budget_from_text(self, text: str) -> str | None:
        match = re.search(r"设置(?:本月|月度|每月)?(.+?)预算\s*(\d+(?:\.\d{1,2})?)", text)
        if not match:
            match = re.search(r"(.+?)预算(?:设置为|设为)?\s*(\d+(?:\.\d{1,2})?)", text)
        if not match:
            return None

        category = _normalize_budget_category(match.group(1))
        amount = float(match.group(2))
        if not category:
            return "你想设置哪个分类的预算？"

        with self.db.connect() as conn:
            book_id = self._ensure_book(conn, "日常账本")
            conn.execute(
                """
                INSERT INTO budgets (book_id, category, amount, period)
                VALUES (?, ?, ?, 'monthly')
                ON CONFLICT(book_id, category, period)
                DO UPDATE SET amount = excluded.amount, updated_at = datetime('now')
                """,
                (book_id, category, amount),
            )
        return f"已设置本月{category}预算：{amount:.2f} 元。"

    def query_budget(self, text: str, now: datetime | None = None) -> LedgerBudgetResult | None:
        if "预算" not in text or not any(token in text for token in ["还剩", "剩余", "用了", "多少"]):
            return None

        now = now or datetime.now()
        category = _category_from_query(text) or _normalize_budget_category(text)
        if not category:
            return None

        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        with self.db.connect() as conn:
            budget = conn.execute(
                """
                SELECT amount
                FROM budgets
                WHERE category = ? AND period = 'monthly'
                ORDER BY book_id IS NOT NULL DESC
                LIMIT 1
                """,
                (category,),
            ).fetchone()
            if not budget:
                return None
            spent = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM ledger_entries
                WHERE entry_type = 'expense'
                    AND category = ?
                    AND occurred_at >= ?
                    AND occurred_at < ?
                """,
                (category, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
            ).fetchone()
        amount = float(budget["amount"])
        spent_total = float(spent["total"])
        return LedgerBudgetResult(
            category=category,
            amount=amount,
            spent=spent_total,
            remaining=amount - spent_total,
            period="本月",
        )

    def search(self, text: str, limit: int = 5) -> list[LedgerSearchItem] | None:
        if not any(token in text for token in ["搜索", "查找", "找账单", "账单里找"]):
            return None
        keyword = text
        for token in ["搜索", "查找", "找账单", "账单里找", "账单", "流水"]:
            keyword = keyword.replace(token, " ")
        keyword = keyword.strip(" ：:，,。")
        if not keyword:
            return []

        like = f"%{keyword}%"
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, amount, category, note, occurred_at
                FROM ledger_entries
                WHERE note LIKE ?
                    OR category LIKE ?
                    OR source_text LIKE ?
                    OR id IN (
                        SELECT ledger_entry_tags.entry_id
                        FROM ledger_entry_tags
                        JOIN ledger_tags ON ledger_tags.id = ledger_entry_tags.tag_id
                        WHERE ledger_tags.name LIKE ?
                    )
                ORDER BY occurred_at DESC, id DESC
                LIMIT ?
                """,
                (like, like, like, like, limit),
            ).fetchall()
        return [
            LedgerSearchItem(
                id=int(row["id"]),
                amount=float(row["amount"]),
                category=str(row["category"]),
                note=str(row["note"]),
                occurred_at=str(row["occurred_at"]),
            )
            for row in rows
        ]

    def set_account_opening_balance_from_text(self, text: str) -> str | None:
        match = re.search(r"设置(.+?)(?:初始余额|余额)\s*(\d+(?:\.\d{1,2})?)", text)
        if not match:
            return None
        account = match.group(1).strip(" ：:，,。")
        amount = float(match.group(2))
        if not account:
            return "你想设置哪个账户的初始余额？"
        with self.db.connect() as conn:
            account_id = self._ensure_account(conn, account)
            conn.execute(
                """
                UPDATE ledger_accounts
                SET opening_balance = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (amount, account_id),
            )
        return f"已设置{account}初始余额：{amount:.2f} 元。"

    def query_account_balance(self, text: str) -> AccountBalanceResult | None:
        if "余额" not in text and "还有多少钱" not in text:
            return None
        account = _extract_account_from_balance_query(text)
        with self.db.connect() as conn:
            if account:
                row = conn.execute(
                    """
                    SELECT id, name, currency, opening_balance
                    FROM ledger_accounts
                    WHERE name = ?
                    """,
                    (account,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, name, currency, opening_balance
                    FROM ledger_accounts
                    WHERE name = '默认账户'
                    """
                ).fetchone()
            if not row:
                return None
            balance = self._account_balance(conn, int(row["id"]), float(row["opening_balance"]))
        return AccountBalanceResult(account=str(row["name"]), balance=balance, currency=str(row["currency"]))

    def manage_category_from_text(self, text: str) -> str | None:
        if any(token in text for token in ["有哪些分类", "分类列表", "查看分类"]):
            with self.db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT name, parent_name, entry_type
                    FROM ledger_categories
                    WHERE status = 'active'
                    ORDER BY parent_name IS NOT NULL, parent_name, name
                    """
                ).fetchall()
            if not rows:
                return "还没有分类。"
            labels = []
            for row in rows:
                parent = f"{row['parent_name']}/" if row["parent_name"] else ""
                labels.append(f"{parent}{row['name']}")
            return "当前分类：" + "、".join(labels)

        match = re.search(r"(?:新增|添加|创建)分类\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,20})(?:\s*(?:属于|归到)\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,20}))?", text)
        if match:
            name = match.group(1)
            parent = match.group(2)
            with self.db.connect() as conn:
                self._ensure_category(conn, parent or name, name if parent else None, "expense")
            return f"已新增分类：{parent + '/' if parent else ''}{name}。"

        match = re.search(r"(?:隐藏|停用)分类\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,20})", text)
        if match:
            name = match.group(1)
            with self.db.connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE ledger_categories
                    SET status = 'hidden', updated_at = datetime('now')
                    WHERE name = ?
                    """,
                    (name,),
                )
            if cursor.rowcount == 0:
                return f"没有找到分类：{name}"
            return f"已隐藏分类：{name}。"

        return None

    def _account_balance(self, conn, account_id: int, opening_balance: float) -> float:
        outgoing = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN entry_type IN ('income', 'refund', 'reimbursement') THEN amount
                    WHEN entry_type IN ('expense', 'transfer') THEN -amount
                    ELSE 0
                END
            ), 0) AS total
            FROM ledger_entries
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()
        incoming_transfer = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM ledger_entries
            WHERE entry_type = 'transfer' AND transfer_to_account_id = ?
            """,
            (account_id,),
        ).fetchone()
        return opening_balance + float(outgoing["total"]) + float(incoming_transfer["total"])

    def create_recurring_from_text(self, text: str) -> str | None:
        if not ("每月" in text and any(token in text for token in ["自动记账", "周期账单", "固定支出", "固定收入"])):
            return None
        day_match = re.search(r"每月\s*(\d{1,2})\s*号", text)
        amount_match = AMOUNT_RE.search(text)
        if not day_match or not amount_match:
            return "周期账单需要包含每月几号和金额，例如：每月1号自动记账房租 3000。"

        day = int(day_match.group(1))
        if day < 1 or day > 31:
            return "每月日期需要在 1 到 31 之间。"

        draft = parse_ledger_text(text.replace("自动记账", " ").replace("周期账单", " "), now=datetime.now())
        if not draft:
            return None
        with self.db.connect() as conn:
            book_id = self._ensure_book(conn, draft.book)
            account_id = self._ensure_account(conn, draft.account)
            cursor = conn.execute(
                """
                INSERT INTO recurring_ledger_entries (
                    book_id, account_id, entry_type, amount, currency,
                    category, note, day_of_month, source_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id,
                    account_id,
                    draft.entry_type,
                    draft.amount,
                    draft.currency,
                    draft.category,
                    draft.note,
                    day,
                    text.strip(),
                ),
            )
            recurring_id = int(cursor.lastrowid)
        return f"已创建周期账单 #{recurring_id}：每月 {day} 号，{draft.note} {draft.amount:.2f} 元。"

    def generate_recurring_due(self, now: datetime | None = None) -> RecurringGenerationResult:
        now = now or datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, last_day = calendar.monthrange(now.year, now.month)
        generated: list[int] = []

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    recurring_ledger_entries.*,
                    COALESCE(ledger_books.name, '日常账本') AS book,
                    COALESCE(ledger_accounts.name, '默认账户') AS account
                FROM recurring_ledger_entries
                LEFT JOIN ledger_books ON ledger_books.id = recurring_ledger_entries.book_id
                LEFT JOIN ledger_accounts ON ledger_accounts.id = recurring_ledger_entries.account_id
                WHERE recurring_ledger_entries.status = 'active'
                    AND (
                        recurring_ledger_entries.last_generated_at IS NULL
                        OR recurring_ledger_entries.last_generated_at < ?
                    )
                ORDER BY recurring_ledger_entries.id
                """,
                (month_start.isoformat(timespec="seconds"),),
            ).fetchall()

        for row in rows:
            day = min(int(row["day_of_month"]), last_day)
            occurred_at = now.replace(day=day, hour=9, minute=0, second=0, microsecond=0)
            if occurred_at > now:
                continue
            draft = LedgerEntryDraft(
                entry_type=row["entry_type"],
                amount=float(row["amount"]),
                currency=row["currency"],
                category=row["category"],
                subcategory=None,
                note=row["note"],
                occurred_at=occurred_at,
                reimbursable=False,
                reimbursement_status="none",
                source_text=row["source_text"],
                book=row["book"],
                account=row["account"],
                tags=("周期账单",),
            )
            entry = self.create(draft)
            generated.append(entry.id)
            with self.db.connect() as conn:
                conn.execute(
                    """
                    UPDATE recurring_ledger_entries
                    SET last_generated_at = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (now.isoformat(timespec="seconds"), row["id"]),
                )

        return RecurringGenerationResult(generated_count=len(generated), entry_ids=tuple(generated))

    def handle_recurring_generation_text(self, text: str) -> str | None:
        if not any(token in text for token in ["生成本月周期账单", "执行周期账单", "生成周期账单"]):
            return None
        result = self.generate_recurring_due()
        if result.generated_count == 0:
            return "没有需要生成的周期账单。"
        ids = "、".join(f"#{entry_id}" for entry_id in result.entry_ids)
        return f"已生成 {result.generated_count} 笔周期账单：{ids}。"

    def budget_warning_for_entry(self, draft: LedgerEntryDraft, now: datetime | None = None) -> str | None:
        if draft.entry_type != "expense":
            return None
        budget = self.query_budget(f"本月{draft.category}预算还剩多少", now=now or draft.occurred_at)
        if not budget:
            return None
        if budget.remaining < 0:
            return f"预算提醒：本月{draft.category}预算已超支 {-budget.remaining:.2f} 元。"
        if budget.amount > 0 and budget.spent / budget.amount >= 0.8:
            return f"预算提醒：本月{draft.category}预算已用 {budget.spent:.2f}/{budget.amount:.2f} 元。"
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
    category_reply = service.manage_category_from_text(text)
    if category_reply:
        return category_reply

    account_set = service.set_account_opening_balance_from_text(text)
    if account_set:
        return account_set

    budget_set = service.set_budget_from_text(text)
    if budget_set:
        return budget_set

    budget = service.query_budget(text)
    if budget:
        return (
            f"{budget.period}{budget.category}预算 {budget.amount:.2f} 元，"
            f"已用 {budget.spent:.2f} 元，还剩 {budget.remaining:.2f} 元。"
        )

    account_balance = service.query_account_balance(text)
    if account_balance:
        return f"{account_balance.account}余额：{account_balance.balance:.2f} {account_balance.currency}。"

    recurring = service.create_recurring_from_text(text)
    if recurring:
        return recurring

    recurring_generation = service.handle_recurring_generation_text(text)
    if recurring_generation:
        return recurring_generation

    search = service.search(text)
    if search is not None:
        if not search:
            return "没有找到匹配的账单。"
        lines = ["找到这些账单："]
        for item in search:
            lines.append(f"- #{item.id} {item.occurred_at[:10]} {item.category} {item.amount:.2f} 元：{item.note}")
        return "\n".join(lines)

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
    dimensions = []
    if draft.account != "默认账户":
        dimensions.append(f"账户：{draft.account}")
    if draft.book != "日常账本":
        dimensions.append(f"账本：{draft.book}")
    if draft.tags:
        dimensions.append("标签：" + "、".join(f"#{tag}" for tag in draft.tags))
    dimension_text = "，" + "，".join(dimensions) if dimensions else ""
    budget_warning = service.budget_warning_for_entry(draft)
    warning_text = f"\n{budget_warning}" if budget_warning else ""
    return (
        f"已记录流水 #{entry.id}：{draft.amount:.2f} 元，"
        f"类型：{_type_label(draft.entry_type)}，分类：{draft.category}，"
        f"备注：{draft.note}{status}{dimension_text}。{warning_text}"
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
    category, _subcategory = _detect_category_detail(text, entry_type)
    return category


def _detect_category_detail(text: str, entry_type: EntryType) -> tuple[str, str | None]:
    if entry_type == "income":
        return "收入", None
    if entry_type == "refund":
        return "退款", None
    if entry_type == "transfer":
        return "转账", None
    if entry_type == "reimbursement":
        return "报销", None
    subcategory_keywords = [
        ("餐饮", "早餐", ["早饭", "早餐"]),
        ("餐饮", "午餐", ["午饭", "午餐"]),
        ("餐饮", "晚餐", ["晚饭", "晚餐"]),
        ("餐饮", "咖啡", ["咖啡", "奶茶"]),
    ]
    for category, subcategory, keywords in subcategory_keywords:
        if any(keyword in text for keyword in keywords):
            return category, subcategory
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category, None
    category_match = re.search(r"(?:分类|归类)[为到]?\s*([\u4e00-\u9fa5A-Za-z0-9_-]{2,12})", text)
    if category_match:
        return category_match.group(1), None
    return "其他", None


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
    note = re.sub(r"#[\w\u4e00-\u9fa5_-]+", " ", note)
    note = re.sub(r"(?:用|从|通过)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})(?:支付|付款|付)?", " ", note)
    note = re.sub(r"(?:记到|放到|归到)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20}账本)", " ", note)
    note = re.sub(r"(?:分类|归类)[为到]?\s*([\u4e00-\u9fa5A-Za-z0-9_-]{2,12})", " ", note)
    for token in ["今天", "昨天", "前天", "花了", "花", "元", "块钱", "块", "待报销", "自动记账", "周期账单"]:
        note = note.replace(token, " ")
    return " ".join(note.split())


def _extract_tags(text: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"#([\w\u4e00-\u9fa5_-]+)", text)]


def _extract_book(text: str) -> str:
    match = re.search(r"(?:记到|放到|归到)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20}账本)", text)
    return match.group(1) if match else "日常账本"


def _extract_account(text: str, entry_type: EntryType) -> str:
    if entry_type == "transfer":
        match = re.search(r"从([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})(?:转到|转入|到)", text)
        if match:
            return match.group(1)
    if entry_type == "income":
        match = re.search(r"(?:到|入账到|到账到)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})", text)
        if match:
            return match.group(1)
    match = re.search(r"(?:用|从|通过)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})(?:支付|付款|付)?", text)
    return match.group(1) if match else "默认账户"


def _extract_transfer_to_account(text: str) -> str | None:
    match = re.search(r"(?:转到|转入|到)([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})", text)
    return match.group(1) if match else None


def _extract_account_from_balance_query(text: str) -> str | None:
    cleaned = text
    for token in ["余额", "还有多少钱", "还剩多少钱", "多少钱", "多少", "查询", "看看", "查"]:
        cleaned = cleaned.replace(token, " ")
    cleaned = cleaned.strip(" ：:，,。")
    return cleaned or None


def _infer_account_type(name: str) -> str:
    if "信用卡" in name or "花呗" in name or "白条" in name:
        return "credit_card"
    if "支付宝" in name or "微信" in name:
        return "wallet"
    if "现金" in name:
        return "cash"
    if "卡" in name:
        return "debit_card"
    return "asset"


def _normalize_budget_category(text: str) -> str:
    cleaned = text
    for token in ["这个月", "本月", "月度", "每月", "预算", "还剩", "剩余", "用了", "多少", "设置"]:
        cleaned = cleaned.replace(token, " ")
    cleaned = cleaned.strip(" ：:，,。")
    category = _category_from_query(cleaned)
    return category or cleaned


def _type_label(entry_type: EntryType) -> str:
    return {
        "expense": "支出",
        "income": "收入",
        "refund": "退款",
        "transfer": "转账",
        "reimbursement": "报销",
    }[entry_type]
