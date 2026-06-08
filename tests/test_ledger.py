from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.services.ledger import LedgerService, handle_ledger_text, parse_ledger_text
from app.storage.db import Database


class LedgerParserTest(unittest.TestCase):
    def test_parse_expense(self) -> None:
        draft = parse_ledger_text("今天午饭 38", now=datetime(2026, 6, 2, 12, 0, 0))
        assert draft is not None
        self.assertEqual(draft.entry_type, "expense")
        self.assertEqual(draft.amount, 38)
        self.assertEqual(draft.category, "餐饮")
        self.assertEqual(draft.note, "午饭")

    def test_parse_income(self) -> None:
        draft = parse_ledger_text("工资到账 12000", now=datetime(2026, 6, 2, 12, 0, 0))
        assert draft is not None
        self.assertEqual(draft.entry_type, "income")
        self.assertEqual(draft.category, "收入")

    def test_parse_reimbursable_expense(self) -> None:
        draft = parse_ledger_text("打车 48，待报销", now=datetime(2026, 6, 2, 12, 0, 0))
        assert draft is not None
        self.assertEqual(draft.entry_type, "expense")
        self.assertEqual(draft.category, "交通")
        self.assertTrue(draft.reimbursable)
        self.assertEqual(draft.reimbursement_status, "pending")

    def test_parse_account_book_and_tags(self) -> None:
        draft = parse_ledger_text("今天午饭 38，用招行信用卡，记到旅行账本 #出差", now=datetime(2026, 6, 2, 12, 0, 0))
        assert draft is not None
        self.assertEqual(draft.category, "餐饮")
        self.assertEqual(draft.subcategory, "午餐")
        self.assertEqual(draft.account, "招行信用卡")
        self.assertEqual(draft.book, "旅行账本")
        self.assertEqual(draft.tags, ("出差",))


class LedgerServiceTest(unittest.TestCase):
    def test_create_and_query_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = LedgerService(db)

            reply = handle_ledger_text("今天午饭 38", service)
            assert reply is not None
            self.assertIn("已记录流水", reply)

            query = service.query("这个月餐饮花了多少", now=datetime.now())
            assert query is not None
            self.assertEqual(query.total, 38)
            self.assertEqual(query.count, 1)

    def test_budget_search_and_recurring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = LedgerService(db)

            reply = handle_ledger_text("今天午饭 38，用招行信用卡 #出差", service)
            assert reply is not None
            self.assertIn("账户：招行信用卡", reply)
            self.assertIn("标签：#出差", reply)

            budget_reply = handle_ledger_text("设置本月餐饮预算 2000", service)
            self.assertEqual(budget_reply, "已设置本月餐饮预算：2000.00 元。")

            budget_query = handle_ledger_text("这个月餐饮还剩多少预算", service)
            assert budget_query is not None
            self.assertIn("还剩 1962.00 元", budget_query)

            search_reply = handle_ledger_text("搜索出差", service)
            assert search_reply is not None
            self.assertIn("午饭", search_reply)

            recurring_reply = handle_ledger_text("每月1号自动记账房租 3000", service)
            assert recurring_reply is not None
            self.assertIn("已创建周期账单", recurring_reply)


if __name__ == "__main__":
    unittest.main()
