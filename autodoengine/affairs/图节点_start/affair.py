"""图节点_start 事务实现。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def execute(config_path: str, **kwargs: Any) -> Dict[str, Any]:
    """执行 start 节点最小事务。

    Args:
        config_path: 事务配置文件绝对路径。
        **kwargs: 预留扩展参数。

    Returns:
        标准事务结果，包含 `output_payload` 与 `artifacts`。

    Raises:
        FileNotFoundError: 配置文件不存在时抛出。

    Examples:
        >>> # doctest: +SKIP
        >>> execute("C:/tmp/config.json")
    """

    _ = kwargs
    resolved_config = Path(config_path).resolve()
    if not resolved_config.exists():
        raise FileNotFoundError(f"配置文件不存在：{resolved_config}")

    config = json.loads(resolved_config.read_text(encoding="utf-8"))
    output_dir = Path(str(config.get("output_dir") or resolved_config.parent)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result_path = output_dir / "start_affair_result.json"
    payload: Dict[str, Any] = {
        "status": "success",
        "affair_uid": "图节点_start",
        "config_path": str(resolved_config),
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "output_payload": {
            "artifacts": [str(result_path)],
            "summary": "engine 内置 start 事务执行完成",
        },
    }
