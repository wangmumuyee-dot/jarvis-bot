from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


@dataclass(frozen=True)
class ParsedReminderTime:
    due_at: datetime | None
    recurrence_rule: str | None


def parse_reminder_time(text: str, now: datetime | None = None) -> ParsedReminderTime:
    now = now or datetime.now()
    recurrence_rule = _parse_recurrence_rule(text)
    if recurrence_rule:
        return ParsedReminderTime(
            due_at=next_recurrence_time(recurrence_rule, now),
            recurrence_rule=recurrence_rule,
        )

    relative = _parse_relative_time(text, now)
    if relative is not None:
        return ParsedReminderTime(due_at=relative, recurrence_rule=None)

    base = _parse_base_date(text, now)
    if base is None:
        return ParsedReminderTime(due_at=None, recurrence_rule=None)

    hour, minute = _parse_time_of_day(text)
    if hour is None:
        return ParsedReminderTime(due_at=base, recurrence_rule=None)

    return ParsedReminderTime(
        due_at=base.replace(hour=hour, minute=minute or 0, second=0, microsecond=0),
        recurrence_rule=None,
    )


def next_recurrence_time(recurrence_rule: str, after: datetime | None = None) -> datetime:
    after = after or datetime.now()
    parts = recurrence_rule.split(":")
    if parts[0] == "daily":
        hour, minute = _split_hhmm(parts[1])
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    if parts[0] == "weekly":
        weekday = int(parts[1])
        hour, minute = _split_hhmm(parts[2])
        days_ahead = (weekday - after.weekday()) % 7
        candidate = (after + timedelta(days=days_ahead)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate <= after:
            candidate += timedelta(days=7)
        return candidate

    raise ValueError(f"Unsupported recurrence rule: {recurrence_rule}")


def _parse_recurrence_rule(text: str) -> str | None:
    hour, minute = _parse_time_of_day(text)
    if hour is None:
        return None

    if "每天" in text or "每日" in text:
        return f"daily:{hour:02d}{minute or 0:02d}"

    match = re.search(r"每周([一二三四五六日天])", text)
    if match:
        weekday = WEEKDAY_MAP[match.group(1)]
        return f"weekly:{weekday}:{hour:02d}{minute or 0:02d}"

    return None


def _parse_base_date(text: str, now: datetime) -> datetime | None:
    if "今天" in text:
        return now.replace(second=0, microsecond=0)
    if "明天" in text:
        return (now + timedelta(days=1)).replace(second=0, microsecond=0)
    if "后天" in text:
        return (now + timedelta(days=2)).replace(second=0, microsecond=0)

    match = re.search(r"下周([一二三四五六日天])", text)
    if match:
        target = WEEKDAY_MAP[match.group(1)]
        days_ahead = (target - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (now + timedelta(days=days_ahead)).replace(second=0, microsecond=0)

    return None


def _parse_relative_time(text: str, now: datetime) -> datetime | None:
    match = re.search(r"(\d+)\s*分钟后", text)
    if match:
        return (now + timedelta(minutes=int(match.group(1)))).replace(second=0, microsecond=0)

    match = re.search(r"(\d+)\s*小时后", text)
    if match:
        return (now + timedelta(hours=int(match.group(1)))).replace(second=0, microsecond=0)

    return None


def _parse_time_of_day(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d{1,2})[:：](\d{1,2})", text)
    if match:
        return _normalize_hour(int(match.group(1)), text), int(match.group(2))

    match = re.search(r"(\d{1,2})\s*点(?:半|(\d{1,2})\s*分?)?", text)
    if match:
        minute = 30 if "点半" in match.group(0) else int(match.group(1 + 1) or 0)
        return _normalize_hour(int(match.group(1)), text), minute

    return None, None


def _normalize_hour(hour: int, text: str) -> int:
    if any(token in text for token in ["下午", "晚上", "傍晚"]) and hour < 12:
        return hour + 12
    if "中午" in text and hour < 11:
        return hour + 12
    if "凌晨" in text and hour == 12:
        return 0
    return hour


def _split_hhmm(value: str) -> tuple[int, int]:
    return int(value[:2]), int(value[2:])
