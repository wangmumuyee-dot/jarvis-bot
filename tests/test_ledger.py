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

    def test_parse_foreign_currency(self) -> None:
        draft = parse_ledger_text("买资料 12美元", now=datetime(2026, 6, 2, 12, 0, 0))
        assert draft is not None
        self.assertEqual(draft.amount, 12)
        self.assertEqual(draft.currency, "USD")
        self.assertEqual(draft.category, "购物")


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

    def test_account_balance_category_and_recurring_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = LedgerService(db)

            self.assertEqual(handle_ledger_text("新增分类 宠物 属于生活", service), "已新增分类：生活/宠物。")
            category_reply = handle_ledger_text("有哪些分类", service)
            assert category_reply is not None
            self.assertIn("生活/宠物", category_reply)

            self.assertEqual(handle_ledger_text("设置招行信用卡初始余额 1000", service), "已设置招行信用卡初始余额：1000.00 元。")
            handle_ledger_text("今天午饭 38，用招行信用卡", service)
            balance = handle_ledger_text("招行信用卡余额多少", service)
            self.assertEqual(balance, "招行信用卡余额：962.00 CNY。")

            handle_ledger_text("每月1号自动记账房租 3000", service)
            generated = service.generate_recurring_due(now=datetime(2026, 6, 8, 12, 0, 0))
            self.assertEqual(generated.generated_count, 1)
            generated_again = service.generate_recurring_due(now=datetime(2026, 6, 8, 12, 0, 0))
            self.assertEqual(generated_again.generated_count, 0)

    def test_budget_warning_after_expense(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = LedgerService(db)

            handle_ledger_text("设置本月餐饮预算 100", service)
            reply = handle_ledger_text("今天午饭 120", service)
            assert reply is not None
            self.assertIn("预算提醒：本月餐饮预算已超支 20.00 元", reply)

    def test_credit_card_debt_settings_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = LedgerService(db)

            card_reply = handle_ledger_text("设置招行信用卡账单日5号还款日25号", service)
            self.assertEqual(card_reply, "已设置招行信用卡：账单日每月 5 号，还款日每月 25 号。")

            card_query = handle_ledger_text("招行信用卡还款日", service)
            self.assertEqual(card_query, "招行信用卡：账单日每月 5 号，还款日每月 25 号。")

            lend_reply = handle_ledger_text("借给小王 500", service)
            assert lend_reply is not None
            self.assertIn("小王欠我 500.00 元", lend_reply)

            repay_reply = handle_ledger_text("小王还我 200", service)
            self.assertEqual(repay_reply, "已更新还款：小王已还 200.00 元，剩余 300.00 元。")

            debt_list = handle_ledger_text("有哪些欠款", service)
            assert debt_list is not None
            self.assertIn("小王欠我 300.00 元", debt_list)

            month_reply = handle_ledger_text("设置每月从5号开始", service)
            self.assertEqual(month_reply, "已设置财务月从每月 5 号开始。")

            week_reply = handle_ledger_text("设置每周从周一开始", service)
            self.assertEqual(week_reply, "已设置财务周从周一开始。")

            settings_reply = handle_ledger_text("财务周期设置", service)
            self.assertEqual(settings_reply, "当前财务周期：每月从 5 号开始，每周从周一开始。")

            handle_ledger_text("今天午饭 38", service)
            handle_ledger_text("工资到账 1000", service)

            stats_reply = handle_ledger_text("本月分类统计", service)
            assert stats_reply is not None
            self.assertIn("餐饮: 38.00 元，1 笔", stats_reply)

            calendar_reply = handle_ledger_text("本月账单日历", service)
            assert calendar_reply is not None
            self.assertIn("支出 38.00 元", calendar_reply)
            self.assertIn("收入 1000.00 元", calendar_reply)


if __name__ == "__main__":
    unittest.main()
