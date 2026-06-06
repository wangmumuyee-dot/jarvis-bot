from __future__ import annotations

import re
from datetime import datetime


def sanitize_filename(value: str, fallback: str = "未命名笔记") -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|#\n\r\t]", " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or fallback)[:80]


def format_frontmatter(data: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            escaped = str(value).replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    return "\n".join(lines)


def now_stamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d %H:%M")

