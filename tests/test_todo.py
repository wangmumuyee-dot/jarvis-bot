from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.todo import TodoContext, TodoService, handle_todo_text
from app.storage.db import Database


class TodoServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        db = Database(Path(self.tmp.name) / "jarvis.db")
        db.init()
        self.service = TodoService(db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_plain_todo(self) -> None:
        reply = handle_todo_text("记一下：买空气炸锅", self.service)
        assert reply is not None
        self.assertIn("已创建待办", reply)
        self.assertIn("买空气炸锅", reply)

    def test_create_timed_reminder(self) -> None:
        created = self.service.create_from_text(
            "明天下午 3 点提醒我交房租",
            context=TodoContext(feishu_open_id="ou_test"),
            now=datetime(2026, 6, 3, 10, 0, 0),
        )
        assert created is not None
        self.assertEqual(created.draft.title, "交房租")
        self.assertEqual(created.draft.due_at, datetime(2026, 6, 4, 15, 0, 0))
        self.assertIsNotNone(created.reminder_id)

    def test_create_relative_reminder(self) -> None:
        created = self.service.create_from_text(
            "5 分钟后提醒我喝水",
            context=TodoContext(feishu_open_id="ou_test"),
            now=datetime(2026, 6, 3, 10, 0, 30),
        )
        assert created is not None
        self.assertEqual(created.draft.title, "喝水")
        self.assertEqual(created.draft.due_at, datetime(2026, 6, 3, 10, 5, 0))

    def test_create_relative_reminder_with_zhihou(self) -> None:
        created = self.service.create_from_text(
            "1分钟之后提醒我看下排骨",
            context=TodoContext(feishu_open_id="ou_test"),
            now=datetime(2026, 6, 3, 10, 0, 30),
        )
        assert created is not None
        self.assertEqual(created.draft.title, "看下排骨")
        self.assertEqual(created.draft.due_at, datetime(2026, 6, 3, 10, 1, 0))
        self.assertIsNotNone(created.reminder_id)

    def test_create_relative_reminder_with_chinese_number(self) -> None:
        created = self.service.create_from_text(
            "两分钟之后提醒我开启 debug 模式",
            context=TodoContext(feishu_open_id="ou_test"),
            now=datetime(2026, 6, 3, 10, 0, 30),
        )
        assert created is not None
        self.assertEqual(created.draft.title, "开启 debug 模式")
        self.assertEqual(created.draft.due_at, datetime(2026, 6, 3, 10, 2, 0))
        self.assertIsNotNone(created.reminder_id)

    def test_complete_todo(self) -> None:
        self.service.create_from_text("记一下：买空气炸锅")
        reply = handle_todo_text("完成买空气炸锅", self.service)
        assert reply is not None
        self.assertIn("已完成待办", reply)
        query = handle_todo_text("全部未完成待办", self.service)
        self.assertEqual(query, "未完成待办为空。")

    def test_process_due_reminder_success(self) -> None:
        now = datetime.now()
        self.service.create_from_text(
            "今天 1 点提醒我测试提醒",
            context=TodoContext(feishu_open_id="ou_test"),
            now=now.replace(hour=0, minute=0, second=0, microsecond=0),
        )

        sent: list[tuple[str, str]] = []
        processed = self.service.process_due_reminders(
            lambda open_id, text: sent.append((open_id, text)),
            now=now + timedelta(days=1),
        )

        self.assertEqual(processed, 1)
        self.assertEqual(sent[0][0], "ou_test")
        self.assertIn("测试提醒", sent[0][1])
        self.assertEqual(self.service.due_reminders(now + timedelta(days=1)), [])

    def test_process_due_reminder_failure_marks_failed(self) -> None:
        now = datetime.now()
        self.service.create_from_text(
            "今天 1 点提醒我测试失败",
            context=TodoContext(feishu_open_id="ou_test"),
            now=now.replace(hour=0, minute=0, second=0, microsecond=0),
        )

        processed = self.service.process_due_reminders(
            lambda _open_id, _text: (_ for _ in ()).throw(RuntimeError("send failed")),
            now=now + timedelta(days=1),
        )

        self.assertEqual(processed, 0)
        due = self.service.due_reminders(now + timedelta(days=1))
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].retry_count, 1)

    def test_recurring_reminder_creates_next_occurrence(self) -> None:
        now = datetime(2026, 6, 3, 8, 0, 0)
        self.service.create_from_text(
            "每天早上 9 点提醒我看计划",
            context=TodoContext(feishu_open_id="ou_test"),
            now=now,
        )

        processed = self.service.process_due_reminders(
            lambda _open_id, _text: None,
            now=datetime(2026, 6, 3, 9, 0, 0),
        )

        self.assertEqual(processed, 1)
        due = self.service.due_reminders(datetime(2026, 6, 4, 9, 0, 0))
        self.assertEqual(len(due), 1)
        self.assertIn("看计划", due[0].title)


if __name__ == "__main__":
    unittest.main()
