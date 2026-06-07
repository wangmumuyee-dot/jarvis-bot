from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Literal

from app.storage.db import Database
from app.utils.time_parse import next_recurrence_time, parse_reminder_time

Priority = Literal["normal", "critical"]


@dataclass(frozen=True)
class TodoContext:
    feishu_open_id: str | None = None
    feishu_user_id: str | None = None


@dataclass(frozen=True)
class TodoDraft:
    title: str
    due_at: datetime | None
    recurrence_rule: str | None
    priority: Priority
    source_text: str
    feishu_open_id: str | None
    feishu_user_id: str | None


@dataclass(frozen=True)
class TodoCreated:
    todo_id: int
    reminder_id: int | None
    draft: TodoDraft


@dataclass(frozen=True)
class DueReminder:
    id: int
    todo_id: int
    title: str
    remind_at: datetime
    recurrence_rule: str | None
    priority: Priority
    retry_count: int
    feishu_open_id: str | None


class TodoService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_from_text(
        self,
        text: str,
        *,
        context: TodoContext | None = None,
        now: datetime | None = None,
    ) -> TodoCreated | None:
        if not _looks_like_todo_create(text):
            return None

        context = context or TodoContext()
        now = now or datetime.now()
        parsed_time = parse_reminder_time(text, now)
        title = _extract_title(text)
        if not title:
            return None

        priority: Priority = "critical" if any(token in text for token in ["关键", "重要", "紧急"]) else "normal"
        draft = TodoDraft(
            title=title,
            due_at=parsed_time.due_at,
            recurrence_rule=parsed_time.recurrence_rule,
            priority=priority,
            source_text=text.strip(),
            feishu_open_id=context.feishu_open_id,
            feishu_user_id=context.feishu_user_id,
        )

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO todos (
                    title, due_at, recurrence_rule, priority,
                    feishu_open_id, feishu_user_id, source_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.title,
                    _dt(draft.due_at),
                    draft.recurrence_rule,
                    draft.priority,
                    draft.feishu_open_id,
                    draft.feishu_user_id,
                    draft.source_text,
                ),
            )
            todo_id = int(cursor.lastrowid)
            reminder_id = None
            if draft.due_at is not None:
                reminder_id = self._insert_reminder(
                    conn,
                    todo_id=todo_id,
                    remind_at=draft.due_at,
                    recurrence_rule=draft.recurrence_rule,
                    priority=draft.priority,
                    feishu_open_id=draft.feishu_open_id,
                )

        return TodoCreated(todo_id=todo_id, reminder_id=reminder_id, draft=draft)

    def complete_from_text(self, text: str) -> str | None:
        if not any(text.startswith(prefix) for prefix in ["完成", "做完", "已完成"]):
            return None
        title = text
        for prefix in ["已完成", "完成", "做完"]:
            title = title.replace(prefix, "", 1).strip(" ：:")
        if not title:
            return "你想完成哪一个待办？"

        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, title
                FROM todos
                WHERE status = 'pending' AND title LIKE ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (f"%{title}%",),
            ).fetchone()
            if not row:
                return f"没有找到匹配的未完成待办：{title}"
            conn.execute(
                """
                UPDATE todos
                SET status = 'done', completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, row["id"]),
            )
            conn.execute(
                """
                UPDATE reminders
                SET status = 'cancelled', updated_at = ?
                WHERE todo_id = ? AND status IN ('pending', 'failed')
                """,
                (now, row["id"]),
            )
        return f"已完成待办 #{row['id']}：{row['title']}"

    def query_from_text(self, text: str, now: datetime | None = None) -> str | None:
        if not _looks_like_todo_query(text):
            return None

        now = now or datetime.now()
        if "今天" in text:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            where = "status = 'pending' AND due_at >= ? AND due_at < ?"
            params: list[object] = [_dt(start), _dt(end)]
            title = "今天待办"
        else:
            where = "status = 'pending'"
            params = []
            title = "未完成待办"

        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, title, due_at, recurrence_rule, priority
                FROM todos
                WHERE {where}
                ORDER BY due_at IS NULL, due_at, created_at DESC
                LIMIT 10
                """,
                params,
            ).fetchall()

        if not rows:
            return f"{title}为空。"

        lines = [f"{title}："]
        for row in rows:
            due = f"（{_format_dt(row['due_at'])}）" if row["due_at"] else ""
            recurrence = "，重复" if row["recurrence_rule"] else ""
            priority = "，关键" if row["priority"] == "critical" else ""
            lines.append(f"- #{row['id']} {row['title']}{due}{recurrence}{priority}")
        return "\n".join(lines)

    def due_reminders(self, now: datetime | None = None, limit: int = 20) -> list[DueReminder]:
        now = now or datetime.now()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    reminders.id,
                    reminders.todo_id,
                    reminders.remind_at,
                    reminders.recurrence_rule,
                    reminders.priority,
                    reminders.retry_count,
                    reminders.feishu_open_id,
                    todos.title
                FROM reminders
                JOIN todos ON todos.id = reminders.todo_id
                WHERE reminders.status IN ('pending', 'failed')
                    AND reminders.remind_at <= ?
                    AND reminders.retry_count < 3
                    AND todos.status = 'pending'
                ORDER BY reminders.remind_at
                LIMIT ?
                """,
                (_dt(now), limit),
            ).fetchall()

        return [
            DueReminder(
                id=int(row["id"]),
                todo_id=int(row["todo_id"]),
                title=str(row["title"]),
                remind_at=datetime.fromisoformat(row["remind_at"]),
                recurrence_rule=row["recurrence_rule"],
                priority=row["priority"],
                retry_count=int(row["retry_count"]),
                feishu_open_id=row["feishu_open_id"],
            )
            for row in rows
        ]

    def process_due_reminders(
        self,
        send_text: Callable[[str, str], None],
        *,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now()
        processed = 0
        for reminder in self.due_reminders(now):
            try:
                if not reminder.feishu_open_id:
                    raise RuntimeError("Reminder has no Feishu open_id")
                send_text(reminder.feishu_open_id, _reminder_text(reminder))
                self.mark_reminder_sent(reminder, now)
                processed += 1
            except Exception as exc:
                self.mark_reminder_failed(reminder.id, str(exc))
        return processed

    def mark_reminder_sent(self, reminder: DueReminder, now: datetime | None = None) -> None:
        now = now or datetime.now()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'sent', sent_at = ?, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (_dt(now), _dt(now), reminder.id),
            )
            if reminder.recurrence_rule:
                next_at = next_recurrence_time(reminder.recurrence_rule, now)
                self._insert_reminder(
                    conn,
                    todo_id=reminder.todo_id,
                    remind_at=next_at,
                    recurrence_rule=reminder.recurrence_rule,
                    priority=reminder.priority,
                    feishu_open_id=reminder.feishu_open_id,
                )

    def mark_reminder_failed(self, reminder_id: int, error: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (error[:500], now, reminder_id),
            )

    def _insert_reminder(
        self,
        conn,
        *,
        todo_id: int,
        remind_at: datetime,
        recurrence_rule: str | None,
        priority: Priority,
        feishu_open_id: str | None,
    ) -> int:
        backup_required = 1 if priority == "critical" else 0
        cursor = conn.execute(
            """
            INSERT INTO reminders (
                todo_id, remind_at, recurrence_rule, priority,
                backup_required, backup_created, feishu_open_id
            )
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                todo_id,
                _dt(remind_at),
                recurrence_rule,
                priority,
                backup_required,
                feishu_open_id,
            ),
        )
        return int(cursor.lastrowid)


def handle_todo_text(
    text: str,
    service: TodoService,
    *,
    context: TodoContext | None = None,
) -> str | None:
    completed = service.complete_from_text(text)
    if completed:
        return completed

    queried = service.query_from_text(text)
    if queried:
        return queried

    created = service.create_from_text(text, context=context)
    if not created:
        return None

    draft = created.draft
    if draft.due_at is None:
        return f"已创建待办 #{created.todo_id}：{draft.title}"

    recurrence = "，重复提醒" if draft.recurrence_rule else ""
    critical = ""
    if draft.priority == "critical":
        critical = " 这是关键提醒，建议你同步设置飞书日历或手机日历作为备用。"
    return (
        f"已创建提醒 #{created.todo_id}：{draft.title}，"
        f"时间：{draft.due_at.strftime('%Y-%m-%d %H:%M')}{recurrence}。{critical}"
    )


def _looks_like_todo_create(text: str) -> bool:
    if any(text.startswith(prefix) for prefix in ["记一下", "记下", "待办"]):
        return True
    return "提醒我" in text or "提醒一下" in text


def _looks_like_todo_query(text: str) -> bool:
    return "待办" in text and any(token in text for token in ["哪些", "查询", "看看", "有什么", "今天", "全部", "未完成"])


def _extract_title(text: str) -> str:
    title = text.strip()
    for prefix in ["记一下", "记下", "待办"]:
        if title.startswith(prefix):
            title = title[len(prefix) :].strip(" ：:")

    for marker in ["提醒我", "提醒一下"]:
        if marker in title:
            title = title.split(marker, 1)[1]

    cleanup_tokens = [
        "今天",
        "明天",
        "后天",
        "下周一",
        "下周二",
        "下周三",
        "下周四",
        "下周五",
        "下周六",
        "下周日",
        "下周天",
        "每天",
        "每日",
        "每周一",
        "每周二",
        "每周三",
        "每周四",
        "每周五",
        "每周六",
        "每周日",
        "每周天",
        "上午",
        "下午",
        "晚上",
        "早上",
        "中午",
        "凌晨",
        "关键",
        "重要",
        "紧急",
    ]
    for token in cleanup_tokens:
        title = title.replace(token, " ")
    title = __import__("re").sub(r"\d{1,2}[:：]\d{1,2}", " ", title)
    title = __import__("re").sub(r"\d{1,2}\s*点(?:半|\d{1,2}\s*分?)?", " ", title)
    title = __import__("re").sub(r"\d+\s*(?:分钟|小时)(?:后|之后)", " ", title)
    return " ".join(title.strip(" ：:，,。").split())


def _reminder_text(reminder: DueReminder) -> str:
    prefix = "关键提醒" if reminder.priority == "critical" else "提醒"
    return f"{prefix}：{reminder.title}"


def _dt(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _format_dt(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
