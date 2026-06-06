from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.summarize import SummaryService, summarize_locally
from app.services.export import LedgerExportService, verify_xlsx
from app.services.knowledge import KnowledgeService
from app.services.ledger import LedgerService, handle_ledger_text
from app.services.todo import TodoContext, TodoService, handle_todo_text
from app.storage.db import Database


class LocalSummaryClient:
    def configured(self) -> bool:
        return False

    def summarize(self, **kwargs):
        return summarize_locally(**kwargs)


def assert_contains(value: str | None, expected: str) -> None:
    if not value or expected not in value:
        raise AssertionError(f"Expected {expected!r} in {value!r}")


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = Database(root / "jarvis.db")
        db.init()
        ledger = LedgerService(db)
        todo = TodoService(db)
        knowledge = KnowledgeService(db, root / "vault", SummaryService(LocalSummaryClient()))
        export = LedgerExportService(db, root / "exports")

        assert_contains(handle_ledger_text("今天午饭 38", ledger), "已记录流水")
        assert_contains(handle_ledger_text("这个月餐饮花了多少？", ledger), "38.00")
        assert_contains(handle_todo_text("记一下：买空气炸锅", todo), "已创建待办")
        assert_contains(
            handle_todo_text(
                "5 分钟后提醒我测试 Day7",
                todo,
                context=TodoContext(feishu_open_id="ou_test"),
            ),
            "已创建提醒",
        )
        assert_contains(handle_todo_text("完成买空气炸锅", todo), "已完成待办")
        note = knowledge.capture_text("整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。")
        if isinstance(note, str) or note is None:
            raise AssertionError(f"Knowledge capture failed: {note}")
        result = export.export("all", now=datetime.now())
        if not verify_xlsx(result.path):
            raise AssertionError("Exported xlsx is invalid")

    print("Day 7 local acceptance check passed.")


if __name__ == "__main__":
    main()

