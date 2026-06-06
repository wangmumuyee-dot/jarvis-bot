from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.storage.db import Database
from app.services.ledger import _type_label

ExportScope = Literal["all", "month", "reimbursable"]


@dataclass(frozen=True)
class ExportResult:
    path: Path
    row_count: int
    scope: ExportScope


class LedgerExportService:
    def __init__(self, db: Database, export_dir: Path) -> None:
        self.db = db
        self.export_dir = export_dir

    def export(self, scope: ExportScope, now: datetime | None = None) -> ExportResult:
        now = now or datetime.now()
        rows = self._rows(scope, now)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        path = self.export_dir / f"ledger-{scope}-{now.strftime('%Y%m%d-%H%M%S')}.xlsx"
        self._write_workbook(path, rows)
        return ExportResult(path=path, row_count=len(rows), scope=scope)

    def _rows(self, scope: ExportScope, now: datetime) -> list[dict[str, object]]:
        where = ""
        params: list[object] = []
        if scope == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
            where = "WHERE occurred_at >= ? AND occurred_at < ?"
            params = [start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")]
        elif scope == "reimbursable":
            where = "WHERE reimbursable = 1 AND reimbursement_status = 'pending'"

        with self.db.connect() as conn:
            records = conn.execute(
                f"""
                SELECT
                    id, entry_type, amount, currency, category, note,
                    occurred_at, reimbursable, reimbursement_status,
                    source_text, created_at
                FROM ledger_entries
                {where}
                ORDER BY occurred_at DESC, id DESC
                """,
                params,
            ).fetchall()
        return [dict(record) for record in records]

    def _write_workbook(self, path: Path, rows: list[dict[str, object]]) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "账本流水"
        headers = [
            "ID",
            "类型",
            "金额",
            "币种",
            "分类",
            "备注",
            "发生时间",
            "是否待报销",
            "报销状态",
            "原始输入",
            "创建时间",
        ]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        for row in rows:
            sheet.append(
                [
                    row["id"],
                    _type_label(row["entry_type"]),
                    row["amount"],
                    row["currency"],
                    row["category"],
                    row["note"],
                    row["occurred_at"],
                    "是" if row["reimbursable"] else "否",
                    row["reimbursement_status"],
                    row["source_text"],
                    row["created_at"],
                ]
            )

        for column in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 10), 36)
        workbook.save(path)


def parse_export_scope(text: str) -> ExportScope | None:
    if "导出" not in text and "Excel" not in text and "excel" not in text and "账单" not in text:
        return None
    if "待报销" in text:
        return "reimbursable"
    if "本月" in text or "这个月" in text:
        return "month"
    return "all"


def handle_export_text(text: str, service: LedgerExportService) -> str | None:
    scope = parse_export_scope(text)
    if not scope:
        return None
    result = service.export(scope)
    return f"已导出账本 Excel：{result.path}，共 {result.row_count} 条记录。"


def verify_xlsx(path: Path) -> bool:
    workbook = load_workbook(path)
    return bool(workbook.sheetnames)

