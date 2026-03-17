"""事务情景标签数据库工具（简版）。

本模块提供最小可用的标签数据库访问能力：
- 从 `config/affair_tags.json` 读取事务标签；
- 根据情景标签快速筛选事务集合；
- 查询单个事务的标签列表。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


def _default_db_path() -> Path:
    """返回默认标签数据库路径。

    Returns:
        默认标签数据库绝对路径。

    Examples:
        >>> _default_db_path().name
        'affair_tags.json'
    """

    return (Path(__file__).resolve().parents[2] / "config" / "affair_tags.json").resolve()


def load_affair_tags(db_path: str | Path | None = None) -> Dict[str, List[str]]:
    """加载事务标签数据库。

    Args:
        db_path: 可选的数据库文件路径；为空时使用默认路径。

    Returns:
        事务到标签列表的映射字典。

    Raises:
        FileNotFoundError: 标签数据库文件不存在。
        ValueError: 文件不是合法 JSON 或结构不符合预期。

    Examples:
        >>> tags = load_affair_tags()
        >>> isinstance(tags, dict)
        True
    """

    path = Path(db_path).resolve() if db_path else _default_db_path()
    if not path.exists():
        raise FileNotFoundError(f"找不到事务标签数据库文件：{path}")

    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"事务标签数据库 JSON 非法：{path}\n{exc}") from exc

    affair_tags = data.get("事务标签")
    if not isinstance(affair_tags, dict):
        raise ValueError(f"事务标签数据库缺少或损坏字段：事务标签（文件：{path}）")

    normalized: Dict[str, List[str]] = {}
    for affair_id, tags in affair_tags.items():
        if not isinstance(affair_id, str):
            continue
        if not isinstance(tags, list):
            continue
        normalized[affair_id] = [str(tag) for tag in tags if str(tag).strip()]

    return normalized


def get_affairs_by_scenario(scenario_name: str, db_path: str | Path | None = None) -> List[str]:
    """根据情景名称获取事务列表。

    Args:
        scenario_name: 情景名称，如“学术研究”“课堂学习”“办公”“基础”。
        db_path: 可选的数据库文件路径。

    Returns:
        按事务名称排序后的事务列表。

    Examples:
        >>> affairs = get_affairs_by_scenario("学术研究")
        >>> isinstance(affairs, list)
        True
    """

    scenario_tag = f"情景:{scenario_name.strip()}"
    affair_tags = load_affair_tags(db_path)

    matched = [
        affair_id
        for affair_id, tags in affair_tags.items()
        if scenario_tag in tags
    ]
    return sorted(matched)


def get_tags_by_affair(affair_id: str, db_path: str | Path | None = None) -> List[str]:
    """查询单个事务的标签列表。

    Args:
        affair_id: 事务标识（通常为事务模块名）。
        db_path: 可选的数据库文件路径。

    Returns:
        标签列表；若事务不存在则返回空列表。

    Examples:
        >>> get_tags_by_affair("print_config")[:1]
        ['情景:基础']
    """

    affair_tags = load_affair_tags(db_path)
    return list(affair_tags.get(affair_id, []))
