from __future__ import annotations

import shutil
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.ai.summarize import SummaryService
from app.services.export import LedgerExportService
from app.services.obsidian_git import ObsidianGitSyncResult
from app.storage.db import Database
from app.utils.markdown import sanitize_filename


@dataclass(frozen=True)
class TemplateExpansion:
    name: str
    command_text: str


class FinanceGitSync(Protocol):
    def sync_note(self, note_path: Path, *, title: str) -> ObsidianGitSyncResult:
        ...


class FinanceP2Service:
    def __init__(
        self,
        db: Database,
        export_service: LedgerExportService,
        vault_path: Path | None = None,
        git_sync: FinanceGitSync | None = None,
        summary_service: SummaryService | None = None,
    ) -> None:
        self.db = db
        self.export_service = export_service
        self.vault_path = vault_path
        self.git_sync = git_sync
        self.summary_service = summary_service

    def expand_quick_template(self, text: str) -> TemplateExpansion | None:
        match = re.search(r"(?:使用|执行|套用)模板\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,24})", text)
        if not match:
            return None
        name = match.group(1)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT command_text FROM quick_templates WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE quick_templates
                SET usage_count = usage_count + 1,
                    updated_at = datetime('now')
                WHERE name = ?
                """,
                (name,),
            )
        return TemplateExpansion(name=name, command_text=str(row["command_text"]))

    def handle_text(self, text: str) -> str | None:
        return (
            self.handle_saving_goal_text(text)
            or self.handle_quick_template_text(text)
            or self.handle_auto_import_text(text)
            or self.handle_monthly_report_text(text)
            or self.handle_consumption_analysis_text(text)
            or self.handle_sync_text(text)
        )

    def handle_saving_goal_text(self, text: str) -> str | None:
        if any(token in text for token in ["愿望清单", "储蓄目标", "存钱目标"]) and any(
            token in text for token in ["列表", "有哪些", "查看"]
        ):
            return self._list_saving_goals()

        match = re.search(
            r"(?:设置|创建|新增)(?:愿望|储蓄|存钱)?(?:目标|基金)?\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,30})\s*(?:目标)?\s*(\d+(?:\.\d{1,2})?)",
            text,
        )
        if match and any(token in text for token in ["愿望", "储蓄", "存钱", "目标"]):
            name = match.group(1).strip(" ：:，,。")
            amount = float(match.group(2))
            return self._upsert_saving_goal(name, amount, text)

        match = re.search(r"(?:为|给)?\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,30})\s*(?:存入|存了|存钱|攒了)\s*(\d+(?:\.\d{1,2})?)", text)
        if match:
            return self._add_saving_progress(match.group(1), float(match.group(2)))

        match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9_-]{1,30})(?:储蓄|存钱|愿望)?进度", text)
        if match:
            return self._saving_goal_progress(_normalize_goal_name(match.group(1)))
        return None

    def handle_quick_template_text(self, text: str) -> str | None:
        use_match = re.search(r"(?:使用|执行|套用)模板\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,24})", text)
        if use_match:
            return f"没有找到快捷模板：{use_match.group(1)}。你可以先说：新增模板 {use_match.group(1)} = 今天午饭 38。"

        if any(token in text for token in ["快捷模板", "常用模板", "模板列表"]) and any(
            token in text for token in ["列表", "有哪些", "查看"]
        ):
            with self.db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT name, command_text, usage_count
                    FROM quick_templates
                    ORDER BY usage_count DESC, updated_at DESC
                    """
                ).fetchall()
            if not rows:
                return "还没有快捷模板。你可以说：新增模板 午饭 = 今天午饭 38。"
            lines = ["快捷模板："]
            for row in rows:
                lines.append(f"- {row['name']}：{row['command_text']}（用过 {row['usage_count']} 次）")
            return "\n".join(lines)

        match = re.search(
            r"(?:新增|创建|设置)(?:快捷)?模板\s*([\u4e00-\u9fa5A-Za-z0-9_-]{1,24})\s*(?:=|：|:)?\s*(.+)",
            text,
        )
        if not match:
            return None
        name = match.group(1).strip(" ：:，,。")
        command_text = match.group(2).strip()
        if not command_text:
            return "模板内容不能为空，例如：新增模板 午饭 = 今天午饭 38。"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO quick_templates (name, command_text)
                VALUES (?, ?)
                ON CONFLICT(name)
                DO UPDATE SET command_text = excluded.command_text,
                    updated_at = datetime('now')
                """,
                (name, command_text),
            )
        return f"已保存快捷模板：{name} -> {command_text}"

    def handle_auto_import_text(self, text: str) -> str | None:
        if not any(token in text for token in ["自动导入账单", "导入账单", "导入Excel", "导入 excel"]):
            return None
        import_dir = self.export_service.export_dir / "imports"
        import_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(path for path in import_dir.glob("*.xlsx") if path.is_file())
        if not files:
            return f"没有找到待导入账单。请把 .xlsx 文件放到：{import_dir}"

        imported_dir = import_dir / "imported"
        imported_dir.mkdir(exist_ok=True)
        lines = ["自动导入账单结果："]
        total_rows = 0
        for path in files:
            try:
                result = self.export_service.import_xlsx(path)
                total_rows += result.row_count
                target = _unique_path(imported_dir / path.name)
                shutil.move(str(path), str(target))
                self._record_import_job(path, "imported", result.row_count, "")
                lines.append(f"- {path.name}: 导入 {result.row_count} 条")
            except Exception as exc:
                self._record_import_job(path, "failed", 0, str(exc))
                lines.append(f"- {path.name}: 失败，{exc}")
        lines.append(f"合计导入 {total_rows} 条。")
        return "\n".join(lines)

    def handle_monthly_report_text(self, text: str, now: datetime | None = None) -> str | None:
        if not any(token in text for token in ["财务月报", "记账月报", "消费月报"]):
            return None
        if not any(token in text for token in ["生成", "写入", "Obsidian", "obsidian"]):
            return None
        if not self.vault_path:
            return "还没有配置 OBSIDIAN_VAULT_PATH，暂时不能写入 Obsidian 财务月报。"

        now = now or datetime.now()
        markdown = self._render_monthly_report(now)
        target_dir = self.vault_path / "02_Areas" / "财务"
        target_dir.mkdir(parents=True, exist_ok=True)
        title = f"{now.strftime('%Y-%m')} 财务月报"
        path = _unique_path(target_dir / f"{sanitize_filename(title)}.md")
        path.write_text(markdown, encoding="utf-8")
        sync_result = self.git_sync.sync_note(path, title=title) if self.git_sync else None
        if sync_result:
            self._record_sync_event("obsidian_finance_report", "ok" if sync_result.ok else "failed", sync_result.message)
        reply = f"已生成 Obsidian 财务月报：{path}"
        if sync_result:
            reply = f"{reply}\nGit 同步：{sync_result.message}" if sync_result.ok else f"{reply}\nGit 同步失败：{sync_result.message}"
        return reply

    def handle_consumption_analysis_text(self, text: str, now: datetime | None = None) -> str | None:
        if not any(token in text for token in ["消费分析", "消费建议", "省钱建议", "分析本月消费"]):
            return None
        return self._render_consumption_analysis(now or datetime.now())

    def handle_sync_text(self, text: str) -> str | None:
        if not any(token in text for token in ["同步状态", "执行同步", "多设备同步", "同步 Obsidian", "同步obsidian"]):
            return None
        if not self.vault_path:
            self._record_sync_event("sync_check", "skipped", "未配置 OBSIDIAN_VAULT_PATH")
            return "还没有配置 OBSIDIAN_VAULT_PATH，无法执行多设备同步检查。"
        if not self.git_sync:
            self._record_sync_event("sync_check", "skipped", "未启用 Obsidian Git 同步")
            return "Obsidian Git 同步未启用。云端部署时可设置 OBSIDIAN_GIT_SYNC_ENABLED=true。"

        marker_dir = self.vault_path / "00_Inbox"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / ".jarvis-sync-check.md"
        marker.write_text(f"# Jarvis Sync Check\n\nupdated_at: {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
        result = self.git_sync.sync_note(marker, title="Jarvis sync check")
        self._record_sync_event("sync_check", "ok" if result.ok else "failed", result.message)
        return f"同步检查：{result.message}"

    def _upsert_saving_goal(self, name: str, amount: float, source_text: str) -> str:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO saving_goals (name, target_amount, currency, source_text)
                VALUES (?, ?, 'CNY', ?)
                ON CONFLICT(name)
                DO UPDATE SET target_amount = excluded.target_amount,
                    status = 'active',
                    updated_at = datetime('now')
                """,
                (name, amount, source_text),
            )
        return f"已设置愿望储蓄：{name}，目标 {amount:.2f} 元。"

    def _add_saving_progress(self, name: str, amount: float) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, target_amount, current_amount FROM saving_goals WHERE name = ? AND status = 'active'",
                (name,),
            ).fetchone()
            if not row:
                return None
            current = float(row["current_amount"]) + amount
            status = "completed" if current >= float(row["target_amount"]) else "active"
            conn.execute(
                """
                UPDATE saving_goals
                SET current_amount = ?,
                    status = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (current, status, row["id"]),
            )
        remaining = max(0.0, float(row["target_amount"]) - current)
        suffix = "，目标已达成。" if status == "completed" else f"，还差 {remaining:.2f} 元。"
        return f"已更新{name}储蓄进度：{current:.2f}/{float(row['target_amount']):.2f} 元{suffix}"

    def _saving_goal_progress(self, name: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT name, target_amount, current_amount, currency, status
                FROM saving_goals
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        if not row:
            return None
        percent = 0.0 if float(row["target_amount"]) == 0 else float(row["current_amount"]) / float(row["target_amount"]) * 100
        return (
            f"{row['name']}储蓄进度：{float(row['current_amount']):.2f}/"
            f"{float(row['target_amount']):.2f} {row['currency']}，{percent:.1f}%，状态：{row['status']}。"
        )

    def _list_saving_goals(self) -> str:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT name, target_amount, current_amount, currency, status
                FROM saving_goals
                ORDER BY status = 'completed', updated_at DESC
                """
            ).fetchall()
        if not rows:
            return "还没有愿望储蓄目标。你可以说：创建愿望目标 相机 5000。"
        lines = ["愿望储蓄："]
        for row in rows:
            percent = 0.0 if float(row["target_amount"]) == 0 else float(row["current_amount"]) / float(row["target_amount"]) * 100
            lines.append(
                f"- {row['name']}: {float(row['current_amount']):.2f}/"
                f"{float(row['target_amount']):.2f} {row['currency']}，{percent:.1f}%，{row['status']}"
            )
        return "\n".join(lines)

    def _render_monthly_report(self, now: datetime) -> str:
        stats = self._month_category_stats(now)
        totals = self._month_totals(now)
        analysis = self._render_consumption_analysis(now)
        stat_lines = "\n".join(f"- {row['category']}: {float(row['total']):.2f} 元，{row['count']} 笔" for row in stats) or "- 暂无"
        return (
            f"# {now.strftime('%Y-%m')} 财务月报\n\n"
            f"## 总览\n\n"
            f"- 支出：{totals['expense']:.2f} 元\n"
            f"- 收入：{totals['income']:.2f} 元\n"
            f"- 净额：{totals['income'] - totals['expense']:.2f} 元\n\n"
            f"## 分类支出\n\n{stat_lines}\n\n"
            f"## 消费分析\n\n{analysis}\n"
        )

    def _render_consumption_analysis(self, now: datetime) -> str:
        stats = self._month_category_stats(now)
        totals = self._month_totals(now)
        if not stats:
            return "本月还没有足够的账单用于消费分析。"
        top = stats[0]
        suggestions = [
            f"本月支出最高的是{top['category']}，共 {float(top['total']):.2f} 元。",
            f"本月收入 {totals['income']:.2f} 元，支出 {totals['expense']:.2f} 元，净额 {totals['income'] - totals['expense']:.2f} 元。",
        ]
        budgets = self._budget_warnings(now)
        if budgets:
            suggestions.extend(budgets)
        else:
            suggestions.append("暂未发现预算超支；可以给高频分类设置月度预算，方便后续主动提醒。")
        suggestions.append("建议优先复盘高频小额消费，并保留房租、学习、健康这类必要支出的备注。")
        local_analysis = "\n".join(f"- {item}" for item in suggestions)
        if not self.summary_service:
            return local_analysis

        summary = self.summary_service.summarize(
            title="本月消费分析",
            content=(
                "请基于以下账本事实，输出适合作为个人 Jarvis 回复的中文消费分析和节省建议。\n"
                f"账本事实：\n{local_analysis}"
            ),
            source_url=None,
        )
        action_items = "\n".join(f"- {item}" for item in summary.action_items[:5])
        if action_items:
            return f"- {summary.summary}\n{action_items}"
        return f"- {summary.summary}"

    def _month_category_stats(self, now: datetime) -> list[dict[str, object]]:
        start, end = _calendar_month_range(now)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
                FROM ledger_entries
                WHERE entry_type = 'expense'
                    AND currency = 'CNY'
                    AND occurred_at >= ?
                    AND occurred_at < ?
                GROUP BY category
                ORDER BY total DESC
                """,
                (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
            ).fetchall()
        return [dict(row) for row in rows]

    def _month_totals(self, now: datetime) -> dict[str, float]:
        start, end = _calendar_month_range(now)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN entry_type = 'expense' AND currency = 'CNY' THEN amount ELSE 0 END), 0) AS expense,
                    COALESCE(SUM(CASE WHEN entry_type IN ('income', 'refund', 'reimbursement') AND currency = 'CNY' THEN amount ELSE 0 END), 0) AS income
                FROM ledger_entries
                WHERE occurred_at >= ? AND occurred_at < ?
                """,
                (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
            ).fetchone()
        return {"expense": float(row["expense"]), "income": float(row["income"])}

    def _budget_warnings(self, now: datetime) -> list[str]:
        start, end = _calendar_month_range(now)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT budgets.category, budgets.amount, COALESCE(SUM(ledger_entries.amount), 0) AS spent
                FROM budgets
                LEFT JOIN ledger_entries ON ledger_entries.category = budgets.category
                    AND ledger_entries.entry_type = 'expense'
                    AND ledger_entries.currency = budgets.currency
                    AND ledger_entries.occurred_at >= ?
                    AND ledger_entries.occurred_at < ?
                WHERE budgets.period = 'monthly'
                GROUP BY budgets.id
                ORDER BY spent / budgets.amount DESC
                """,
                (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
            ).fetchall()
        warnings = []
        for row in rows:
            amount = float(row["amount"])
            spent = float(row["spent"])
            if amount > 0 and spent > amount:
                warnings.append(f"{row['category']}预算已超支 {spent - amount:.2f} 元。")
            elif amount > 0 and spent / amount >= 0.8:
                warnings.append(f"{row['category']}预算已用 {spent:.2f}/{amount:.2f} 元，接近上限。")
        return warnings

    def _record_import_job(self, path: Path, status: str, row_count: int, last_error: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO import_jobs (file_path, status, row_count, last_error)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_path)
                DO UPDATE SET status = excluded.status,
                    row_count = excluded.row_count,
                    last_error = excluded.last_error,
                    updated_at = datetime('now')
                """,
                (str(path), status, row_count, last_error),
            )

    def _record_sync_event(self, kind: str, status: str, message: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_events (kind, status, message)
                VALUES (?, ?, ?)
                """,
                (kind, status, message),
            )


def handle_finance_p2_text(text: str, service: FinanceP2Service) -> str | None:
    return service.handle_text(text)


def _calendar_month_range(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique path for {path}")


def _normalize_goal_name(name: str) -> str:
    cleaned = name.strip(" ：:，,。")
    for suffix in ["储蓄", "存钱", "愿望", "目标", "基金"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned
