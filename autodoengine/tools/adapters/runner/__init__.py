"""Runner adapter。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from autodoengine.tools.public.facade import invoke_capability


def run_capability_from_params_file(params_file: str | Path) -> Dict[str, Any]:
    """从参数文件运行 capability。

    Args:
        params_file: 参数文件路径。

    Returns:
        协议结果字典。
    """

    params_path = Path(params_file).resolve()
    payload = json.loads(params_path.read_text(encoding="utf-8"))
    capability_id = str(payload.get("capability_id") or "").strip()
    capability_payload = dict(payload.get("payload") or {}) if isinstance(payload.get("payload"), dict) else {}
    caller_context = dict(payload.get("caller_context") or {}) if isinstance(payload.get("caller_context"), dict) else {}
    workspace_root = payload.get("workspace_root")
    allow_internal = bool(payload.get("allow_internal", False))
    return invoke_capability(
        capability_id,
        payload=capability_payload,
        caller_context=caller_context,
        allow_internal=allow_internal,
        workspace_root=workspace_root,
    )


__all__ = ["run_capability_from_params_file"]
