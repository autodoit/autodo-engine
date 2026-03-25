"""引擎能力巡检事务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from autodoengine.tools.public.facade import invoke_capability


def execute(config_path: str, **kwargs: Any) -> Dict[str, Any]:
    """执行引擎能力巡检。

    Args:
        config_path: 配置文件路径。
        **kwargs: 预留扩展参数。

    Returns:
        标准事务结果。
    """

    _ = kwargs
    resolved_config = Path(config_path).resolve()
    config = json.loads(resolved_config.read_text(encoding="utf-8"))
    workspace_root = str(config.get("_workspace_root") or config.get("workspace_root") or Path.cwd())
    output_dir = Path(str(config.get("output_dir") or resolved_config.parent / "output")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    refresh_result = invoke_capability(
        "affair_refresh",
        payload={"workspace_root": workspace_root, "strict": bool(config.get("strict", False))},
        caller_context={"caller_source": "affair:引擎能力巡检"},
        workspace_root=workspace_root,
    )
    paths_result = invoke_capability(
        "affair_show_paths",
        payload={"workspace_root": workspace_root},
        caller_context={"caller_source": "affair:引擎能力巡检"},
        workspace_root=workspace_root,
    )

    result_path = output_dir / "engine_capability_inspection_result.json"
    result_payload = {
        "status": "success",
        "refresh_result": refresh_result,
        "paths_result": paths_result,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "success",
        "output_payload": {
            "artifacts": [str(result_path)],
            "summary": "引擎能力巡检完成",
        },
    }
