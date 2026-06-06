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
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_occurred_at
ON ledger_entries(occurred_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_category
ON ledger_entries(category);

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
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

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
