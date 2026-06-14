from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_host: str
    app_port: int
    log_level: str
    database_path: Path
    export_dir: Path
    reminder_scan_interval_seconds: int
    web_auth_token: str
    obsidian_vault_path: Path | None
    obsidian_git_sync_enabled: bool
    obsidian_git_push_enabled: bool
    feishu_app_id: str
    feishu_app_secret: str
    feishu_verification_token: str
    feishu_encrypt_key: str
    allowed_feishu_user_ids: set[str]
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_responses_path: str
    llm_timeout_seconds: int

    @property
    def feishu_configured(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    obsidian_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_path=Path(os.getenv("DATABASE_PATH", "data/jarvis.db")),
        export_dir=Path(os.getenv("EXPORT_DIR", "data/exports")),
        reminder_scan_interval_seconds=int(os.getenv("REMINDER_SCAN_INTERVAL_SECONDS", "60")),
        web_auth_token=os.getenv("WEB_AUTH_TOKEN", ""),
        obsidian_vault_path=Path(obsidian_path) if obsidian_path else None,
        obsidian_git_sync_enabled=_bool_env("OBSIDIAN_GIT_SYNC_ENABLED"),
        obsidian_git_push_enabled=_bool_env("OBSIDIAN_GIT_PUSH_ENABLED", True),
        feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        feishu_verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
        feishu_encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
        allowed_feishu_user_ids=_split_csv(os.getenv("ALLOWED_FEISHU_USER_IDS")),
        llm_provider=os.getenv("LLM_PROVIDER", "openai-compatible"),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        llm_base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        llm_responses_path=os.getenv("LLM_RESPONSES_PATH", "/responses"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS", "20")),
    )
