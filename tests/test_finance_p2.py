from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from app.ai.summarize import SummaryResult
from app.services.export import LedgerExportService
from app.services.finance_p2 import FinanceP2Service, handle_finance_p2_text
from app.services.ledger import LedgerService, handle_ledger_text
from app.services.obsidian_git import ObsidianGitSyncResult
from app.storage.db import Database


class FakeGitSync:
    def sync_note(self, note_path: Path, *, title: str) -> ObsidianGitSyncResult:
        return ObsidianGitSyncResult(True, f"fake synced {title}: {note_path.name}")


class FakeSummaryService:
    def __init__(self) -> None:
        self.called = False

    def summarize(self, *, title: str, content: str, source_url: str | None = None) -> SummaryResult:
        self.called = True
        return SummaryResult(
            title=title,
            summary="AI 版消费分析：餐饮支出接近预算，需要控制外食频率。",
            key_points=[],
            action_items=["本周减少两次外卖", "继续记录高频小额消费"],
            tags=["财务"],
            related=["财务"],
        )


class FinanceP2ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "jarvis.db")
        self.db.init()
        self.export_service = LedgerExportService(self.db, self.root / "exports")
        self.service = FinanceP2Service(
            self.db,
            self.export_service,
            self.root / "vault",
            git_sync=FakeGitSync(),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_saving_goal_and_template(self) -> None:
        reply = handle_finance_p2_text("创建愿望目标 相机 5000", self.service)
        self.assertEqual(reply, "已设置愿望储蓄：相机，目标 5000.00 元。")

        progress = handle_finance_p2_text("为相机存钱 1200", self.service)
        self.assertEqual(progress, "已更新相机储蓄进度：1200.00/5000.00 元，还差 3800.00 元。")

        query = handle_finance_p2_text("相机储蓄进度", self.service)
        assert query is not None
        self.assertIn("24.0%", query)

        template = handle_finance_p2_text("新增模板 午饭 = 今天午饭 38", self.service)
        self.assertEqual(template, "已保存快捷模板：午饭 -> 今天午饭 38")

        expansion = self.service.expand_quick_template("使用模板 午饭")
        assert expansion is not None
        self.assertEqual(expansion.command_text, "今天午饭 38")

    def test_route_executes_quick_template(self) -> None:
        import app.main as main

        original_finance_p2 = main.finance_p2_service
        original_ledger = main.ledger_service
        main.finance_p2_service = self.service
        main.ledger_service = LedgerService(self.db)
        try:
            self.assertEqual(main.route_text("新增模板 午饭 = 今天午饭 38"), "已保存快捷模板：午饭 -> 今天午饭 38")
            reply = main.route_text("使用模板 午饭")
        finally:
            main.finance_p2_service = original_finance_p2
            main.ledger_service = original_ledger

        self.assertIn("已使用模板「午饭」", reply)
        self.assertIn("已记录流水", reply)

    def test_auto_import_report_analysis_and_sync(self) -> None:
        ledger = LedgerService(self.db)
        handle_ledger_text("设置本月餐饮预算 100", ledger)
        handle_ledger_text("今天午饭 88", ledger)
        handle_ledger_text("工资到账 1000", ledger)

        import_dir = self.root / "exports" / "imports"
        import_dir.mkdir(parents=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["账本", "账户", "金额", "分类", "备注", "标签"])
        sheet.append(["日常账本", "默认账户", 12, "餐饮", "咖啡", "日常"])
        workbook.save(import_dir / "bill.xlsx")

        import_reply = handle_finance_p2_text("自动导入账单", self.service)
        assert import_reply is not None
        self.assertIn("导入 1 条", import_reply)
        self.assertTrue((import_dir / "imported" / "bill.xlsx").exists())

        analysis = handle_finance_p2_text("分析本月消费", self.service)
        assert analysis is not None
        self.assertIn("本月支出最高的是餐饮", analysis)
        self.assertIn("预算已用", analysis)

        report = self.service.handle_monthly_report_text("生成本月财务月报", now=datetime(2026, 6, 9, 12, 0, 0))
        assert report is not None
        self.assertIn("已生成 Obsidian 财务月报", report)
        files = list((self.root / "vault" / "02_Areas" / "财务").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("消费分析", files[0].read_text(encoding="utf-8"))

        sync = handle_finance_p2_text("同步状态", self.service)
        assert sync is not None
        self.assertIn("fake synced Jarvis sync check", sync)

    def test_consumption_analysis_uses_summary_service_when_available(self) -> None:
        summary = FakeSummaryService()
        service = FinanceP2Service(
            self.db,
            self.export_service,
            self.root / "vault",
            summary_service=summary,  # type: ignore[arg-type]
        )
        ledger = LedgerService(self.db)
        handle_ledger_text("今天午饭 88", ledger)

        reply = handle_finance_p2_text("分析本月消费", service)
        assert reply is not None
        self.assertTrue(summary.called)
        self.assertIn("AI 版消费分析", reply)
        self.assertIn("本周减少两次外卖", reply)


if __name__ == "__main__":
    unittest.main()
