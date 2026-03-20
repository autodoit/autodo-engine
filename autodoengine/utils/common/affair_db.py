"""事务数据库读写工具。

本模块负责事务数据库 JSON 的统一读写与基础结构构造。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict


def now_iso() -> str:
    """返回 UTC ISO8601 时间字符串。

    Returns:
        当前 UTC 时间字符串。

    Examples:
        >>> isinstance(now_iso(), str)
        True
    """

    return datetime.now(UTC).isoformat()


def create_empty_registry(*, schema_version: str) -> Dict[str, Any]:
    """创建空事务数据库结构。

    Args:
        schema_version: 数据结构版本号。

    Returns:
        空数据库字典。

    Examples:
        >>> db = create_empty_registry(schema_version="2026-03-12")
        >>> db["records"]
        []
    """

    return {
        "schema_version": schema_version,
        "generated_at": now_iso(),
        "registry_role": "affair_management_system",
        "records": [],
        "stats": {
            "aok_graph": 0,
            "aok_business": 0,
            "user_business": 0,
            "invalid": 0,
            "total": 0,
        },
    }


def load_registry(db_path: Path, *, schema_version: str) -> Dict[str, Any]:
    """读取事务数据库文件。

    Args:
        db_path: 数据库文件路径。
        schema_version: 默认结构版本号。

    Returns:
        数据库字典；文件不存在时返回空结构。

    Raises:
        ValueError: 文件存在但内容非法时抛出。

    Examples:
        >>> from pathlib import Path
        >>> _ = load_registry(Path("not-exists.json"), schema_version="2026-03-12")
    """

    if not db_path.exists():
        return create_empty_registry(schema_version=schema_version)

    try:
        data = json.loads(db_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"读取事务数据库失败：{db_path}：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"事务数据库必须是 JSON 对象：{db_path}")

    if not isinstance(data.get("records"), list):
        data["records"] = []
    if not isinstance(data.get("stats"), dict):
        data["stats"] = {}

    data.setdefault("schema_version", schema_version)
    data.setdefault("generated_at", now_iso())
    data.setdefault("registry_role", "affair_management_system")
    data["stats"].setdefault("aok_graph", 0)
    data["stats"].setdefault("aok_business", 0)
    data["stats"].setdefault("user_business", 0)
    data["stats"].setdefault("invalid", 0)
    data["stats"].setdefault("total", len(data.get("records") or []))
    return data


def save_registry(db_path: Path, data: Dict[str, Any]) -> None:
    """保存事务数据库文件。

    Args:
        db_path: 数据库文件路径。
        data: 数据库字典。

    Returns:
        None。

    Examples:
        >>> from pathlib import Path
        >>> path = Path("tmp_affair_registry.json")
        >>> save_registry(path, create_empty_registry(schema_version="2026-03-12"))
    """

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
