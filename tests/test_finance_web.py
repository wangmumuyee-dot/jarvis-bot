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
