"""统一时间工具（默认北京时间）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE_NAME = "Asia/Shanghai"


def resolve_timezone_name(timezone_name: str | None = None) -> str:
    text = str(timezone_name or "").strip()
    return text or DEFAULT_TIMEZONE_NAME


def resolve_timezone(timezone_name: str | None = None) -> ZoneInfo:
    return ZoneInfo(resolve_timezone_name(timezone_name))


def now_dt(timezone_name: str | None = None) -> datetime:
    return datetime.now(tz=resolve_timezone(timezone_name))


def now_iso(timezone_name: str | None = None, *, timespec: str | None = None) -> str:
    current = now_dt(timezone_name)
    if timespec:
        return current.isoformat(timespec=timespec)
    return current.isoformat()


def now_compact(timezone_name: str | None = None, fmt: str = "%Y%m%dT%H%M%S") -> str:
    return now_dt(timezone_name).strftime(fmt)


__all__ = [
    "DEFAULT_TIMEZONE_NAME",
    "resolve_timezone_name",
    "resolve_timezone",
    "now_dt",
    "now_iso",
    "now_compact",
]
