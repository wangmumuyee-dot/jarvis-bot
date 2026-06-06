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


if __name__ == "__main__":
    unittest.main()

