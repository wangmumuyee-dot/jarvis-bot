from __future__ import annotations

import tempfile
import unittest
import base64
import json
from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook

from app.services.export import LedgerExportService
from app.services.finance_p2 import FinanceP2Service
from app.services.finance_web import FinanceEntryInput, FinanceWebService
from app.services.ledger import LedgerService, parse_ledger_text
from app.storage.db import Database


class FinanceWebServiceTest(unittest.TestCase):
    def test_create_entry_updates_dashboard_and_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            ledger = LedgerService(db)
            service = FinanceWebService(db, ledger)

            created = service.create_entry(
                FinanceEntryInput(
                    entry_type="expense",
                    amount=38,
                    currency="CNY",
                    category="餐饮",
                    note="网页午饭",
                    occurred_at=None,
                    account="默认账户",
                    book="日常账本",
                    tags=("web",),
                )
            )

            self.assertIn("已记录流水", created["reply"])

            dashboard = service.dashboard()
            self.assertEqual(dashboard["totals"]["expense"], 38)
            self.assertEqual(dashboard["totals"]["count"], 1)

            entries = service.entries()
            self.assertEqual(entries[0]["note"], "网页午饭")
            self.assertEqual(entries[0]["tags"], ["web"])

    def test_upsert_account_returns_balances_for_web_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            ledger = LedgerService(db)
            service = FinanceWebService(db, ledger)

            saved = service.upsert_account(
                name="招商储蓄卡",
                account_type="debit_card",
                currency="CNY",
                opening_balance=1000,
            )
            self.assertIn("已保存账户", saved["reply"])

            service.create_entry(
                FinanceEntryInput(
                    entry_type="expense",
                    amount=38,
                    currency="CNY",
                    category="餐饮",
                    note="午饭",
                    account="招商储蓄卡",
                )
            )

            accounts = service.options()["accounts"]
            account = next(item for item in accounts if item["name"] == "招商储蓄卡")
            self.assertEqual(account["account_type"], "debit_card")
            self.assertEqual(account["opening_balance"], 1000)
            self.assertEqual(account["balance"], 962)

    def test_dashboard_includes_total_assets_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            ledger = LedgerService(db)
            service = FinanceWebService(db, ledger)

            service.upsert_account(
                name="现金",
                account_type="cash",
                currency="CNY",
                opening_balance=1000,
            )
            service.upsert_account(
                name="备用金",
                account_type="wallet",
                currency="CNY",
                opening_balance=200,
            )
            service.create_entry(
                FinanceEntryInput(
                    entry_type="expense",
                    amount=80,
                    currency="CNY",
                    category="餐饮",
                    note="晚饭",
                    account="现金",
                )
            )

            dashboard = service.dashboard()
            self.assertEqual(dashboard["assets"]["primary_currency"], "CNY")
            self.assertEqual(dashboard["assets"]["primary_total"], 1120)
            self.assertEqual(len(dashboard["assets"]["accounts"]), 3)
            self.assertTrue(any(item["name"] == "现金" and item["balance"] == 920 for item in dashboard["assets"]["accounts"]))

    def test_edit_account_by_id_updates_existing_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = FinanceWebService(db, LedgerService(db))

            account = service.upsert_account(
                name="旧钱包",
                account_type="wallet",
                currency="CNY",
                opening_balance=10,
            )["account"]
            updated = service.upsert_account(
                account_id=int(account["id"]),
                name="新钱包",
                account_type="cash",
                currency="CNY",
                opening_balance=20,
            )["account"]

            self.assertEqual(updated["id"], account["id"])
            self.assertEqual(updated["name"], "新钱包")
            self.assertEqual(updated["account_type"], "cash")
            accounts = service.options()["accounts"]
            self.assertFalse(any(item["name"] == "旧钱包" for item in accounts))
            self.assertTrue(any(item["name"] == "新钱包" for item in accounts))

            with self.assertRaises(ValueError):
                service.upsert_account(
                    account_id=1,
                    name="默认账户2",
                    account_type="asset",
                    currency="CNY",
                    opening_balance=0,
                )

    def test_delete_account_removes_unused_and_archives_used_or_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = FinanceWebService(db, LedgerService(db))

            unused = service.upsert_account(
                name="临时钱包",
                account_type="wallet",
                currency="CNY",
                opening_balance=10,
            )["account"]
            deleted = service.delete_account(int(unused["id"]))
            self.assertIn("已删除账户", deleted["reply"])
            self.assertFalse(any(item["name"] == "临时钱包" for item in service.options()["accounts"]))

            used = service.upsert_account(
                name="已用账户",
                account_type="asset",
                currency="CNY",
                opening_balance=100,
            )["account"]
            service.create_entry(
                FinanceEntryInput(
                    entry_type="expense",
                    amount=8,
                    currency="CNY",
                    category="餐饮",
                    note="早餐",
                    account="已用账户",
                )
            )
            archived = service.delete_account(int(used["id"]))
            self.assertIn("已归档账户", archived["reply"])
            self.assertFalse(any(item["name"] == "已用账户" for item in service.options()["accounts"]))

            default_deleted = service.delete_account(1)
            self.assertIn("已删除账户", default_deleted["reply"])
            self.assertFalse(any(item["name"] == "默认账户" for item in service.options()["accounts"]))

    def test_update_and_delete_entry_from_web(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = FinanceWebService(db, LedgerService(db))

            created = service.create_entry(
                FinanceEntryInput(
                    entry_type="expense",
                    amount=20,
                    currency="CNY",
                    category="餐饮",
                    note="午饭",
                    account="默认账户",
                    tags=("old",),
                )
            )
            updated = service.update_entry(
                int(created["id"]),
                FinanceEntryInput(
                    entry_type="income",
                    amount=88,
                    currency="CNY",
                    category="收入",
                    note="红包",
                    account="现金",
                    tags=("new",),
                ),
            )
            self.assertIn("已更新流水", updated["reply"])
            entry = service.entries()[0]
            self.assertEqual(entry["entry_type"], "income")
            self.assertEqual(entry["amount"], 88)
            self.assertEqual(entry["note"], "红包")
            self.assertEqual(entry["account"], "现金")
            self.assertEqual(entry["tags"], ["new"])

            deleted = service.delete_entry(int(created["id"]))
            self.assertIn("已删除流水", deleted["reply"])
            self.assertEqual(service.entries(), [])

    def test_web_token_guard_rejects_missing_token_when_configured(self) -> None:
        import app.main as main

        original = main.settings
        main.settings = replace(main.settings, web_auth_token="secret-token")
        try:
            with self.assertRaises(HTTPException):
                main._verify_finance_web_access(None)
            self.assertIsNone(main._verify_finance_web_access("secret-token"))
        finally:
            main.settings = original

    def test_export_endpoint_returns_xlsx_response(self) -> None:
        import app.main as main

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            ledger = LedgerService(db)
            export = LedgerExportService(db, Path(tmp) / "exports")
            draft = parse_ledger_text("今天午饭 18")
            assert draft is not None
            ledger.create(draft)

            original_export = main.export_service
            main.export_service = export
            try:
                response = main.finance_export_file(scope="month", redact=False)
                self.assertTrue(Path(response.path).exists())
                self.assertTrue(str(response.path).endswith(".xlsx"))
            finally:
                main.export_service = original_export

    def test_import_endpoint_uploads_xlsx_and_creates_entries(self) -> None:
        import app.main as main

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            export = LedgerExportService(db, Path(tmp) / "exports")
            upload = Path(tmp) / "upload.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["备注", "金额"])
            sheet.append(["网页导入午饭", 9])
            workbook.save(upload)

            original_ledger = main.ledger_service
            original_export = main.export_service
            original_p2 = main.finance_p2_service
            main.ledger_service = LedgerService(db)
            main.export_service = export
            main.finance_p2_service = FinanceP2Service(db, export)
            try:
                payload = main.FinanceImportRequest(
                    filename="upload.xlsx",
                    content_base64=base64.b64encode(upload.read_bytes()).decode("ascii"),
                )
                reply = main.finance_import_file(payload)["reply"]
                self.assertIn("合计导入 1 条", reply)
                with db.connect() as conn:
                    row = conn.execute("SELECT note, amount FROM ledger_entries").fetchone()
                self.assertEqual(row["note"], "网页导入午饭")
                self.assertEqual(float(row["amount"]), 9)
            finally:
                main.ledger_service = original_ledger
                main.export_service = original_export
                main.finance_p2_service = original_p2

    def test_account_endpoint_saves_account(self) -> None:
        import app.main as main

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "jarvis.db")
            db.init()
            service = FinanceWebService(db, LedgerService(db))
            original_service = main.finance_web_service
            main.finance_web_service = service
            try:
                payload = main.FinanceAccountRequest(
                    name="现金",
                    account_type="cash",
                    currency="CNY",
                    opening_balance=200,
                )
                result = main.finance_upsert_account(payload)
                self.assertEqual(result["account"]["name"], "现金")
                self.assertEqual(result["account"]["balance"], 200)
                deleted = main.finance_delete_account(int(result["account"]["id"]))
                self.assertIn("已删除账户", deleted["reply"])
            finally:
                main.finance_web_service = original_service

    def test_pwa_assets_are_available_for_installation(self) -> None:
        import app.main as main

        manifest = json.loads((main.WEB_STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["start_url"], "/finance")
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue((main.WEB_STATIC_DIR / "icons" / "apple-touch-icon.png").exists())
        self.assertTrue((main.WEB_STATIC_DIR / "icons" / "icon-192.png").exists())
        self.assertTrue((main.WEB_STATIC_DIR / "icons" / "icon-512.png").exists())

        response = main.finance_service_worker()
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")


if __name__ == "__main__":
    unittest.main()
