from __future__ import annotations

from getpass import getpass
from pathlib import Path


ENV_PATH = Path(".env")
EXAMPLE_PATH = Path(".env.example")


FIELDS = [
    ("DATABASE_PATH", "SQLite 数据库路径", "data/jarvis.db", False),
    ("EXPORT_DIR", "Excel 导出目录", "data/exports", False),
    ("OBSIDIAN_VAULT_PATH", "Obsidian vault 绝对路径", "", False),
    ("OBSIDIAN_GIT_SYNC_ENABLED", "Obsidian 写入后自动 Git 同步", "false", False),
    ("OBSIDIAN_GIT_PUSH_ENABLED", "Obsidian Git 同步后自动 push", "true", False),
    ("FEISHU_APP_ID", "飞书 App ID", "", False),
    ("FEISHU_APP_SECRET", "飞书 App Secret", "", True),
    ("FEISHU_VERIFICATION_TOKEN", "飞书 Verification Token", "", True),
    ("ALLOWED_FEISHU_USER_IDS", "允许的飞书 user_id/open_id，多个用逗号分隔", "", False),
    ("LLM_PROVIDER", "大模型厂商标识", "openai-compatible", False),
    ("LLM_API_KEY", "大模型 API Key，可留空使用本地规则", "", True),
    ("LLM_MODEL", "大模型模型名", "gpt-4.1-mini", False),
    ("LLM_BASE_URL", "OpenAI-compatible API base URL", "https://api.openai.com/v1", False),
    ("LLM_RESPONSES_PATH", "Responses API 路径", "/responses", False),
    ("LLM_TIMEOUT_SECONDS", "大模型请求超时秒数", "20", False),
    ("REMINDER_SCAN_INTERVAL_SECONDS", "提醒扫描间隔秒数", "60", False),
]


def main() -> None:
    values = _read_env(EXAMPLE_PATH)
    values.update(_read_env(ENV_PATH))
    _migrate_legacy_llm_values(values)

    print("配置 .env。直接回车会保留当前值；敏感值不会显示。")
    for key, label, default, secret in FIELDS:
        current = values.get(key, default)
        current_display = "***已设置***" if secret and current else current
        prompt = f"{label} [{current_display}]: "
        if secret:
            entered = getpass(prompt)
        else:
            entered = input(prompt)
        if entered.strip():
            values[key] = entered.strip()
        elif key not in values:
            values[key] = default

    _write_env(values)
    print(f"已写入 {ENV_PATH}")
    print("下一步运行：python scripts/preflight_check.py")


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def _migrate_legacy_llm_values(values: dict[str, str]) -> None:
    legacy_pairs = {
        "LLM_API_KEY": "OPENAI_API_KEY",
        "LLM_MODEL": "OPENAI_MODEL",
        "LLM_BASE_URL": "OPENAI_BASE_URL",
        "LLM_TIMEOUT_SECONDS": "OPENAI_TIMEOUT_SECONDS",
    }
    for new_key, old_key in legacy_pairs.items():
        if not values.get(new_key) and values.get(old_key):
            values[new_key] = values[old_key]


def _write_env(values: dict[str, str]) -> None:
    sections = [
        (
            "App",
            [
                "APP_ENV",
                "APP_HOST",
                "APP_PORT",
                "LOG_LEVEL",
                "REMINDER_SCAN_INTERVAL_SECONDS",
            ],
        ),
        (
            "Storage",
            [
                "DATABASE_PATH",
                "EXPORT_DIR",
                "OBSIDIAN_VAULT_PATH",
                "OBSIDIAN_GIT_SYNC_ENABLED",
                "OBSIDIAN_GIT_PUSH_ENABLED",
            ],
        ),
        (
            "Feishu",
            [
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "FEISHU_VERIFICATION_TOKEN",
                "FEISHU_ENCRYPT_KEY",
                "ALLOWED_FEISHU_USER_IDS",
            ],
        ),
        (
            "LLM",
            [
                "LLM_PROVIDER",
                "LLM_API_KEY",
                "LLM_MODEL",
                "LLM_BASE_URL",
                "LLM_RESPONSES_PATH",
                "LLM_TIMEOUT_SECONDS",
            ],
        ),
    ]
    lines: list[str] = []
    defaults = _read_env(EXAMPLE_PATH)
    defaults.update(values)
    for title, keys in sections:
        lines.append(f"# {title}")
        for key in keys:
            lines.append(f"{key}={defaults.get(key, '')}")
        lines.append("")
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
