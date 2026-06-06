from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def main() -> None:
    checks = run_checks()
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    if any(check.status == "FAIL" for check in checks):
        raise SystemExit(1)


def run_checks() -> list[Check]:
    settings = get_settings()
    checks = [
        _check_env_file(),
        _check_database(settings.database_path),
        _check_obsidian(settings.obsidian_vault_path),
        _check_obsidian_git(settings),
        _check_export_dir(settings.export_dir),
        _check_logs_dir(),
        _check_cloudflared(),
        _check_feishu_env(settings),
        _check_llm_env(settings),
    ]
    checks.extend(_check_pmset())
    return checks


def _check_env_file() -> Check:
    env_path = PROJECT_ROOT / ".env"
    return Check(".env", "PASS" if env_path.exists() else "WARN", str(env_path) if env_path.exists() else "未找到 .env，可从 .env.example 复制")


def _check_database(path: Path) -> Check:
    if not path.exists():
        return Check("SQLite", "WARN", f"数据库不存在，运行 python scripts/init_db.py 初始化：{path}")
    try:
        with sqlite3.connect(path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as exc:
        return Check("SQLite", "FAIL", f"数据库无法打开：{exc}")
    required = {"ledger_entries", "todos", "reminders", "knowledge_notes"}
    missing = sorted(required - tables)
    if missing:
        return Check("SQLite", "FAIL", f"缺少表：{', '.join(missing)}")
    return Check("SQLite", "PASS", str(path))


def _check_obsidian(path: Path | None) -> Check:
    if not path:
        return Check("Obsidian", "WARN", "未配置 OBSIDIAN_VAULT_PATH，知识库写入和链接总结不可用")
    if not path.exists():
        return Check("Obsidian", "FAIL", f"路径不存在：{path}")
    if not path.is_dir():
        return Check("Obsidian", "FAIL", f"不是目录：{path}")
    return Check("Obsidian", "PASS", str(path))


def _check_obsidian_git(settings) -> Check:
    if not settings.obsidian_git_sync_enabled:
        return Check("Obsidian Git", "PASS", "未启用自动 Git 同步")
    path = settings.obsidian_vault_path
    if not path:
        return Check("Obsidian Git", "FAIL", "已启用 Git 同步，但未配置 OBSIDIAN_VAULT_PATH")
    try:
        repo = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if repo.returncode != 0 or repo.stdout.strip() != "true":
            return Check("Obsidian Git", "FAIL", f"vault 不是 Git 仓库：{path}")
        status = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return Check("Obsidian Git", "FAIL", f"无法检查 Git 状态：{exc}")
    if status.returncode != 0:
        return Check("Obsidian Git", "FAIL", status.stderr.strip() or status.stdout.strip())
    dirty = "有未提交变更" if status.stdout.strip() else "工作区干净"
    push = "push=on" if settings.obsidian_git_push_enabled else "push=off"
    return Check("Obsidian Git", "PASS", f"{dirty}, {push}")


def _check_export_dir(path: Path) -> Check:
    path.mkdir(parents=True, exist_ok=True)
    return Check("Excel export dir", "PASS", str(path))


def _check_logs_dir() -> Check:
    logs = PROJECT_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return Check("logs", "PASS", str(logs))


def _check_cloudflared() -> Check:
    path = shutil.which("cloudflared")
    if not path:
        return Check("cloudflared", "WARN", "未找到 cloudflared；飞书 webhook 本地联调需要它或 ngrok")
    return Check("cloudflared", "PASS", path)


def _check_feishu_env(settings) -> Check:
    missing = []
    if not settings.feishu_app_id:
        missing.append("FEISHU_APP_ID")
    if not settings.feishu_app_secret:
        missing.append("FEISHU_APP_SECRET")
    if missing:
        return Check("Feishu env", "WARN", f"缺少：{', '.join(missing)}")
    return Check("Feishu env", "PASS", "App ID/Secret 已配置")


def _check_llm_env(settings) -> Check:
    if not settings.llm_api_key:
        return Check("LLM env", "WARN", "未配置 LLM_API_KEY，将使用本地规则 fallback")
    return Check("LLM env", "PASS", f"provider={settings.llm_provider}, model={settings.llm_model}")


def _check_pmset() -> list[Check]:
    if sys.platform != "darwin":
        return [Check("power settings", "WARN", "非 macOS，跳过 pmset 检查")]
    try:
        output = subprocess.check_output(["pmset", "-g"], text=True, timeout=5)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        return [Check("power settings", "WARN", f"无法运行 pmset：{exc}")]

    checks: list[Check] = []
    sleep_value = _pmset_value(output, "sleep")
    displaysleep_value = _pmset_value(output, "displaysleep")
    powernap_value = _pmset_value(output, "powernap")

    if sleep_value is None:
        checks.append(Check("system sleep", "WARN", "未能读取 sleep 配置"))
    elif sleep_value == "0":
        checks.append(Check("system sleep", "PASS", "sleep=0，系统休眠已关闭"))
    else:
        checks.append(Check("system sleep", "WARN", f"sleep={sleep_value}，建议旧笔记本试用期间关闭自动休眠"))

    if displaysleep_value:
        checks.append(Check("display sleep", "PASS", f"displaysleep={displaysleep_value}，屏幕休眠不影响服务"))
    if powernap_value:
        checks.append(Check("powernap", "PASS", f"powernap={powernap_value}"))
    return checks


def _pmset_value(output: str, key: str) -> str | None:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key} "):
            return stripped.split()[-1]
    return None


if __name__ == "__main__":
    main()
