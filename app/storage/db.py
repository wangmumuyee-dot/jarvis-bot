from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS processed_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_message_id TEXT,
    event_id TEXT,
    processed_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL,
    UNIQUE(feishu_message_id),
    UNIQUE(event_id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER,
    account_id INTEGER,
    category_id INTEGER,
    transfer_to_account_id INTEGER,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('expense', 'income', 'refund', 'transfer', 'reimbursement')
    ),
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    category TEXT NOT NULL,
    note TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    reimbursable INTEGER NOT NULL DEFAULT 0,
    reimbursement_status TEXT NOT NULL DEFAULT 'none' CHECK (
        reimbursement_status IN ('none', 'pending', 'received')
    ),
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(book_id) REFERENCES ledger_books(id),
    FOREIGN KEY(account_id) REFERENCES ledger_accounts(id),
    FOREIGN KEY(category_id) REFERENCES ledger_categories(id),
    FOREIGN KEY(transfer_to_account_id) REFERENCES ledger_accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_occurred_at
ON ledger_entries(occurred_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_category
ON ledger_entries(category);

CREATE TABLE IF NOT EXISTS ledger_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'archived')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    account_type TEXT NOT NULL DEFAULT 'asset' CHECK (
        account_type IN ('asset', 'cash', 'debit_card', 'credit_card', 'wallet', 'liability', 'other')
    ),
    currency TEXT NOT NULL DEFAULT 'CNY',
    opening_balance REAL NOT NULL DEFAULT 0,
    statement_day INTEGER,
    repayment_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'archived')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_name TEXT,
    entry_type TEXT NOT NULL DEFAULT 'expense' CHECK (
        entry_type IN ('expense', 'income', 'refund', 'transfer', 'reimbursement')
    ),
    icon TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'hidden')
    ),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, parent_name, entry_type)
);

CREATE TABLE IF NOT EXISTS ledger_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_entry_tags (
    entry_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(entry_id, tag_id),
    FOREIGN KEY(entry_id) REFERENCES ledger_entries(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES ledger_tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER,
    category TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    period TEXT NOT NULL DEFAULT 'monthly' CHECK (
        period IN ('monthly', 'yearly')
    ),
    currency TEXT NOT NULL DEFAULT 'CNY',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_id, category, period),
    FOREIGN KEY(book_id) REFERENCES ledger_books(id)
);

CREATE TABLE IF NOT EXISTS recurring_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER,
    account_id INTEGER,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('expense', 'income', 'refund', 'transfer', 'reimbursement')
    ),
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    category TEXT NOT NULL,
    note TEXT NOT NULL,
    day_of_month INTEGER NOT NULL CHECK (day_of_month >= 1 AND day_of_month <= 31),
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'paused', 'archived')
    ),
    last_generated_at TEXT,
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(book_id) REFERENCES ledger_books(id),
    FOREIGN KEY(account_id) REFERENCES ledger_accounts(id)
);

CREATE TABLE IF NOT EXISTS ledger_debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_type TEXT NOT NULL CHECK (
        debt_type IN ('lend', 'borrow')
    ),
    person TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    repaid_amount REAL NOT NULL DEFAULT 0 CHECK (repaid_amount >= 0),
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'settled', 'cancelled')
    ),
    due_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ledger_debts_status_person
ON ledger_debts(status, person);

CREATE TABLE IF NOT EXISTS finance_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saving_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    target_amount REAL NOT NULL CHECK (target_amount >= 0),
    current_amount REAL NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'completed', 'archived')
    ),
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quick_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    command_text TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'imported', 'failed')
    ),
    row_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('ok', 'failed', 'skipped')
    ),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'done', 'cancelled')
    ),
    due_at TEXT,
    recurrence_rule TEXT,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (
        priority IN ('normal', 'critical')
    ),
    feishu_open_id TEXT,
    feishu_user_id TEXT,
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_todos_status_due_at
ON todos(status, due_at);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id INTEGER NOT NULL,
    remind_at TEXT NOT NULL,
    recurrence_rule TEXT,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (
        priority IN ('normal', 'critical')
    ),
    backup_required INTEGER NOT NULL DEFAULT 0,
    backup_created INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'sent', 'failed', 'acknowledged', 'cancelled')
    ),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_at TEXT,
    feishu_open_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(todo_id) REFERENCES todos(id)
);

CREATE INDEX IF NOT EXISTS idx_reminders_status_remind_at
ON reminders(status, remind_at);

CREATE TABLE IF NOT EXISTS knowledge_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('text', 'link')
    ),
    source_url TEXT,
    obsidian_path TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    related TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_notes_created_at
ON knowledge_notes(created_at);

CREATE TABLE IF NOT EXISTS health_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sex TEXT,
    age INTEGER,
    height_cm REAL,
    weight_kg REAL,
    goal TEXT NOT NULL DEFAULT '',
    workout_days_per_week INTEGER,
    equipment TEXT NOT NULL DEFAULT '',
    injuries TEXT NOT NULL DEFAULT '',
    diet_preferences TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS health_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_type TEXT NOT NULL CHECK (
        plan_type IN ('workout', 'meal')
    ),
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    content TEXT NOT NULL,
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_health_plans_type_start
ON health_plans(plan_type, start_date);

CREATE TABLE IF NOT EXISTS health_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkin_date TEXT NOT NULL,
    weight_kg REAL,
    sleep_hours REAL,
    workout_done TEXT NOT NULL DEFAULT '',
    meal_notes TEXT NOT NULL DEFAULT '',
    fatigue_level INTEGER,
    mood TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_health_checkins_date
ON health_checkins(checkin_date);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            _migrate_ledger_entries(conn)
            _migrate_ledger_accounts(conn)
            _seed_ledger_defaults(conn)
            _seed_finance_settings(conn)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _migrate_ledger_entries(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(ledger_entries)").fetchall()}
    migrations = {
        "book_id": "ALTER TABLE ledger_entries ADD COLUMN book_id INTEGER",
        "account_id": "ALTER TABLE ledger_entries ADD COLUMN account_id INTEGER",
        "category_id": "ALTER TABLE ledger_entries ADD COLUMN category_id INTEGER",
        "transfer_to_account_id": "ALTER TABLE ledger_entries ADD COLUMN transfer_to_account_id INTEGER",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ledger_entries_book_account
        ON ledger_entries(book_id, account_id)
        """
    )


def _migrate_ledger_accounts(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(ledger_accounts)").fetchall()}
    migrations = {
        "account_type": "ALTER TABLE ledger_accounts ADD COLUMN account_type TEXT NOT NULL DEFAULT 'asset'",
        "currency": "ALTER TABLE ledger_accounts ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'",
        "opening_balance": "ALTER TABLE ledger_accounts ADD COLUMN opening_balance REAL NOT NULL DEFAULT 0",
        "statement_day": "ALTER TABLE ledger_accounts ADD COLUMN statement_day INTEGER",
        "repayment_day": "ALTER TABLE ledger_accounts ADD COLUMN repayment_day INTEGER",
        "status": "ALTER TABLE ledger_accounts ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "created_at": "ALTER TABLE ledger_accounts ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
        "updated_at": "ALTER TABLE ledger_accounts ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _seed_ledger_defaults(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO ledger_books (id, name)
        VALUES (1, '日常账本')
        """
    )


def _seed_finance_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "base_currency": "CNY",
        "week_start_day": "1",
        "month_start_day": "1",
    }
    for key, value in defaults.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO finance_settings (key, value)
            VALUES (?, ?)
            """,
            (key, value),
        )
    conn.execute(
        """
        INSERT OR IGNORE INTO ledger_accounts (id, name, account_type)
        VALUES (1, '默认账户', 'asset')
        """
    )
    categories = [
        ("餐饮", None, "expense"),
        ("早餐", "餐饮", "expense"),
        ("午餐", "餐饮", "expense"),
        ("晚餐", "餐饮", "expense"),
        ("咖啡", "餐饮", "expense"),
        ("交通", None, "expense"),
        ("购物", None, "expense"),
        ("学习", None, "expense"),
        ("健康", None, "expense"),
        ("居住", None, "expense"),
        ("娱乐", None, "expense"),
        ("其他", None, "expense"),
        ("收入", None, "income"),
        ("退款", None, "refund"),
        ("转账", None, "transfer"),
        ("报销", None, "reimbursement"),
    ]
    for name, parent_name, entry_type in categories:
        conn.execute(
            """
            INSERT OR IGNORE INTO ledger_categories (name, parent_name, entry_type)
            VALUES (?, ?, ?)
            """,
            (name, parent_name, entry_type),
        )
    conn.execute(
        """
        UPDATE ledger_entries
        SET book_id = COALESCE(book_id, 1),
            account_id = COALESCE(account_id, 1)
        """
    )
