from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMClientConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    responses_path: str
    timeout_seconds: int

    @property
    def responses_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/{self.responses_path.lstrip('/')}"

    def configured(self) -> bool:
        return bool(self.api_key)
