"""引擎运行时探针事务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from autodoengine.tools.public.facade import invoke_capability


def execute(config_path: str, **kwargs: Any) -> Dict[str, Any]:
    """执行运行时探针。

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
    runtime_base_dir = Path(str(config.get("runtime_base_dir") or resolved_config.parent / "runtime_probe")).resolve()
    output_dir = Path(str(config.get("output_dir") or resolved_config.parent / "output")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_result = invoke_capability(
        "runtime_bootstrap",
        payload={"base_dir": str(runtime_base_dir)},
        caller_context={"caller_source": "affair:引擎运行时探针"},
        workspace_root=workspace_root,
    )
    path_result = invoke_capability(
        "runtime_show_paths",
        payload={"base_dir": str(runtime_base_dir)},
        caller_context={"caller_source": "affair:引擎运行时探针"},
        workspace_root=workspace_root,
    )

    result_path = output_dir / "engine_runtime_probe_result.json"
    result_payload = {
        "status": "success",
        "bootstrap_result": bootstrap_result,
        "path_result": path_result,
    }
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "success",
        "output_payload": {
            "artifacts": [str(result_path)],
            "summary": "引擎运行时探针完成",
        },
    }
