"""v4 对外公开 API。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from hashlib import sha256
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from autodoengine.core.enums import DecisionType, TaskAction, TaskStatus
from autodoengine.core.types import DecisionResult
from autodoengine.flow_graph import load_graph_from_file
from autodoengine.flow_graph.models import Graph
from autodoengine.scheduling.task_loop import run_task_step as _run_task_step
from autodoengine.scheduling.task_loop import run_task_until_terminal as _run_task_until_terminal
from autodoengine.scheduling.task_loop import run_task_until_wait as _run_task_until_wait
from autodoengine.taskdb import bootstrap_runtime_storage
from autodoengine.taskdb import graph_registry, task_store
from autodoengine.taskdb.department_store import (
    get_department as _get_department,
    list_department_members as _list_department_members,
    list_departments as _list_departments,
)
from autodoengine.taskdb.request_store import (
    acquire_request_lease as _acquire_request_lease,
    create_request as _create_request,
    get_request as _get_request,
    list_schedulable_requests as _list_schedulable_requests,
    list_requests as _list_requests,
    list_task_requests as _list_task_requests,
    mark_request_committed as _mark_request_committed,
    mark_request_blocked as _mark_request_blocked,
    mark_request_completed as _mark_request_completed,
    mark_request_failed as _mark_request_failed,
    mark_request_ready_for_commit as _mark_request_ready_for_commit,
    mark_request_running as _mark_request_running,
    release_request_lease as _release_request_lease,
    renew_request_lease as _renew_request_lease,
    upsert_executor_heartbeat as _upsert_executor_heartbeat,
    请求状态_已完成,
    请求状态_已失败,
    请求状态_已阻断,
    请求状态_待租约,
    请求状态_待调度,
    请求状态_已租约,
    请求状态_待提交,
    请求状态_已提交,
)
from autodoengine.taskdb import (
    append_decision,
    build_blocked_governance_view as _build_blocked_governance_view,
    build_decision_department_view as _build_decision_department_view,
    build_task_full_chain_view as _build_task_full_chain_view,
)
from autodoengine.taskdb import log_store
from autodoengine.taskdb.storage_paths import get_runtime_store_dirs, get_runtime_store_files
from autodoengine.utils.affair_registry import build_registry, resolve_runner
from autodoengine.utils.common.affair_manager import import_user_affair as _import_user_affair
from autodoengine.utils.common.affair_sync import SCHEMA_VERSION, build_runtime_registry, get_affair_registry_paths as _get_affair_registry_paths, sync_affair_databases
from autodoengine.utils.path_tools import (
    load_json_or_py,
    resolve_paths_to_absolute,
    resolve_paths_to_absolute_with_audit,
    resolve_portable_path,
)
from autodoengine.utils.runtime_context import get_runtime_context, set_runtime_context


def _load_tools_module() -> Any:
    """按需加载工具模块。

    Returns:
        优先返回 `autodokit.tools`，未安装时回退到 `autodoengine.tools`。

    Raises:
        ModuleNotFoundError: 当外部与内置工具模块均不可用时抛出。
    """

    try:
        return importlib.import_module("autodokit.tools")
    except ModuleNotFoundError:
        try:
            return importlib.import_module("autodoengine.tools")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "未找到可用工具模块（autodokit.tools/autodoengine.tools）。"
            ) from exc


def _load_tools_module_with_attrs(*required_attrs: str) -> Any:
    """加载满足指定接口的工具模块。

    Args:
        *required_attrs: 必须存在的属性名。

    Returns:
        满足接口要求的工具模块。

    Raises:
        KeyError: 当没有模块满足要求时抛出。
    """

    candidates: list[Any] = []
    for module_name in ("autodokit.tools", "autodoengine.tools"):
        try:
            candidates.append(importlib.import_module(module_name))
        except ModuleNotFoundError:
            continue

    for module in candidates:
        if all(hasattr(module, attr) for attr in required_attrs):
            return module

    raise KeyError(f"工具模块未提供所需接口：{', '.join(required_attrs)}")


def _normalize_workspace_root(workspace_root: str | Path | None) -> Path:
    """规范化工作区根目录。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        绝对路径形式的工作区根目录。
    """

    if workspace_root is None:
        return Path.cwd().resolve()
    return resolve_portable_path(str(workspace_root), base_dir=Path.cwd())


def _resolve_public_argument(*pairs: tuple[str, Any], required: bool = False) -> Any:
    """解析公开 API 的中英文别名形参。"""

    selected_name = ""
    selected_value: Any = None
    has_value = False

    for name, value in pairs:
        if value is None:
            continue
        if has_value and value != selected_value:
            raise ValueError(f"{selected_name} 与 {name} 不能同时传入不同值")
        if not has_value:
            selected_name = name
            selected_value = value
            has_value = True

    if required and not has_value:
        names = " / ".join(name for name, _ in pairs)
        raise ValueError(f"{names} 不能为空")
    return selected_value


def _normalize_affair_outputs(result: Any) -> List[Path]:
    """将事务返回结果归一化为路径列表。

    Args:
        result: 事务返回值。

    Returns:
        路径对象列表。
    """

    if result is None:
        return []

    if isinstance(result, dict):
        payload = result.get("output_payload") if isinstance(result.get("output_payload"), dict) else {}
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
        return [Path(str(item)) for item in artifacts]

    if isinstance(result, (str, Path)):
        return [Path(str(result))]

    if isinstance(result, list):
        return [Path(str(item)) for item in result]

    if isinstance(result, tuple):
        return [Path(str(item)) for item in result]

    return [Path(str(result))]


def _normalize_affair_receipt(
    *,
    outputs: list[Path],
    affair_uid: str,
    request_uid: str,
    node_code: str,
    task_uid: str | None,
    executor_uid: str,
) -> Dict[str, Any]:
    """把事务输出归一化为统一回执结构。"""

    payload_from_file: dict[str, Any] | None = None
    for output_path in outputs:
        if str(output_path.suffix).lower() != ".json":
            continue
        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            payload_from_file = raw
            break

    if payload_from_file is not None and {
        "result_code",
        "message",
        "output_payload",
        "executor_meta",
    }.issubset(set(payload_from_file.keys())):
        receipt = dict(payload_from_file)
        receipt.setdefault("result_code", "PASS")
        receipt.setdefault("message", "事务执行完成")
        receipt.setdefault("output_payload", {})
        receipt.setdefault("executor_meta", {})
        if not isinstance(receipt.get("output_payload"), dict):
            receipt["output_payload"] = {"raw_output_payload": receipt.get("output_payload")}
        if not isinstance(receipt.get("executor_meta"), dict):
            receipt["executor_meta"] = {"raw_executor_meta": receipt.get("executor_meta")}
        receipt["output_payload"].setdefault("artifacts", [str(item) for item in outputs])
        return receipt

    return {
        "result_code": "PASS",
        "message": "事务执行完成",
        "output_payload": {
            "artifacts": [str(item) for item in outputs],
            "affair_uid": affair_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "task_uid": task_uid,
        },
        "executor_meta": {
            "executor_uid": executor_uid,
            "receipt_source": "outputs",
        },
    }


@contextmanager
def _runtime_context_scope(*, workspace_root: Path, affair_uid: str, config_path: Path) -> Any:
    """临时注入运行时上下文并在退出时恢复。"""

    previous_context = get_runtime_context()
    global_config_path = workspace_root / "config" / "config.json"
    if not global_config_path.exists():
        global_config_path = None

    set_runtime_context(
        global_config_path=global_config_path,
        current_affair_uid=affair_uid,
        current_affair_config_path=config_path,
    )
    try:
        yield
    finally:
        set_runtime_context(
            global_config_path=previous_context.global_config_path,
            current_affair_uid=previous_context.current_affair_uid,
            current_affair_config_path=previous_context.current_affair_config_path,
        )


def _serialize_dataclass_or_value(value: Any) -> Any:
    """序列化 dataclass 或原始值。

    Args:
        value: 待序列化对象。

    Returns:
        适合 JSON 输出的对象。
    """

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def _load_module_from_file(source_py_path: str | Path) -> Any:
    """按源码文件路径加载事务模块。

    Args:
        source_py_path: 事务源码路径。

    Returns:
        Python 模块对象。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ImportError: 文件无法加载为模块时抛出。
    """

    source_path = resolve_portable_path(str(source_py_path), base_dir=Path.cwd())
    if not source_path.exists():
        raise FileNotFoundError(f"事务源码文件不存在：{source_path}")

    module_name = f"autodoengine_dynamic_affair_{sha256(str(source_path).encode('utf-8')).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载事务源码模块：{source_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_graph(文件路径: str | Path | None = None, *, file_path: str | Path | None = None) -> Graph:
    """公开的图加载入口。

    Args:
        file_path: 静态图 JSON 文件路径。

    Returns:
        Graph: 图对象。

    Raises:
        FileNotFoundError: 当文件不存在时抛出。

    Examples:
        >>> # doctest: +SKIP
        >>> graph = load_graph("demos/data/graph.json")
    """

    target = resolve_portable_path(
        _resolve_public_argument(("文件路径", 文件路径), ("file_path", file_path), required=True),
        base_dir=Path.cwd(),
    )
    if not target.exists():
        raise FileNotFoundError(f"图文件不存在：{target}")
    return load_graph_from_file(str(target))


def bootstrap_runtime(运行时根目录: str | Path | None = None, *, base_dir: str | Path | None = None) -> None:
    """公开的运行时初始化入口。"""

    bootstrap_runtime_storage(
        _resolve_public_argument(("运行时根目录", 运行时根目录), ("base_dir", base_dir), required=True)
    )


def register_graph(graph: Graph) -> None:
    """公开的图注册入口。"""

    graph_registry.register_graph(graph)


def create_task(title: str, goal_text: str, current_node_uid: str, parent_task_uid: str | None = None) -> dict[str, object]:
    """公开的任务创建入口。"""

    return task_store.create_task(
        title=title,
        goal_text=goal_text,
        current_node_uid=current_node_uid,
        parent_task_uid=parent_task_uid,
    )


def create_task_request(
    request_type: str,
    target_affair_uid: str,
    payload: dict[str, Any] | None = None,
    task_uid: str | None = None,
    source_object_type: str = "",
    source_object_uid: str = "",
    node_code: str = "",
    config_path: str = "",
    priority_score: float = 0.0,
    source: str = "任务系统",
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    resource_fingerprint: str = "",
    idempotency_key: str = "",
    expected_version: str = "",
    snapshot_token: str = "",
) -> Dict[str, Any]:
    """创建事务请求。"""

    return _create_request(
        request_type=request_type,
        target_affair_uid=target_affair_uid,
        payload=payload,
        task_uid=task_uid,
        source_object_type=source_object_type,
        source_object_uid=source_object_uid,
        node_code=node_code,
        config_path=config_path,
        priority_score=priority_score,
        source=source,
        request_contract=request_contract,
        metadata=metadata,
        resource_fingerprint=resource_fingerprint,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        snapshot_token=snapshot_token,
    )


def create_task_request_from_project_node(
    *,
    project_config_path: str | Path,
    node_code: str,
    task_uid: str | None = None,
    request_type: str = "事务执行",
    target_affair_uid: str | None = None,
    source_object_type: str = "节点",
    source_object_uid: str | None = None,
    priority_score: float = 0.0,
    source: str = "项目经理",
    payload: dict[str, Any] | None = None,
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """根据项目级配置与节点编码构造标准事务请求。"""

    resolved_project_config_path = resolve_portable_path(str(project_config_path), base_dir=Path.cwd())
    project_config = load_json_or_py(resolved_project_config_path)

    normalized_node_code = str(node_code or "").strip().upper()
    if not normalized_node_code:
        raise ValueError("node_code 不能为空")

    node_inputs = project_config.get("node_inputs")
    if not isinstance(node_inputs, dict):
        raise KeyError("项目配置缺少 node_inputs")
    if normalized_node_code not in node_inputs:
        raise KeyError(f"node_inputs 中不存在节点：{normalized_node_code}")

    workspace_root_text = str(project_config.get("workspace_root") or "").strip()
    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=resolved_project_config_path.parent)
        if workspace_root_text
        else resolved_project_config_path.parent
    )
    resolved_node_config_path = resolve_portable_path(str(node_inputs[normalized_node_code]), base_dir=workspace_root)

    node_contracts = project_config.get("node_contracts")
    project_node_contract = (
        dict(node_contracts.get(normalized_node_code) or {})
        if isinstance(node_contracts, dict) and isinstance(node_contracts.get(normalized_node_code), dict)
        else {}
    )
    merged_request_contract = dict(project_node_contract)
    merged_request_contract.update(dict(request_contract or {}))

    resolved_affair_uid = str(target_affair_uid or "").strip()
    if not resolved_affair_uid:
        paths_payload = project_config.get("paths")
        registry_path_text = str((paths_payload or {}).get("affair_entry_registry_path") or "").strip()
        if registry_path_text:
            resolved_registry_path = resolve_portable_path(registry_path_text, base_dir=workspace_root)
            registry_payload = load_json_or_py(resolved_registry_path)
            for item in registry_payload.get("records", []):
                if not isinstance(item, dict):
                    continue
                record_node_code = str(item.get("node_code") or "").strip().upper()
                affair_uid = str(item.get("affair_uid") or "").strip()
                if record_node_code == normalized_node_code and affair_uid:
                    resolved_affair_uid = affair_uid
                    break
    if not resolved_affair_uid:
        raise KeyError(f"无法为节点推断 target_affair_uid：{normalized_node_code}")

    next_payload = dict(payload or {})
    next_payload.setdefault("workspace_root", str(workspace_root))
    next_payload.setdefault("project_config_path", str(resolved_project_config_path))
    next_payload.setdefault("node_config_path", str(resolved_node_config_path))

    next_metadata = dict(metadata or {})
    next_metadata.setdefault("project_config_path", str(resolved_project_config_path))
    next_metadata.setdefault("workspace_root", str(workspace_root))
    next_metadata.setdefault("node_code", normalized_node_code)

    return create_task_request(
        request_type=request_type,
        target_affair_uid=resolved_affair_uid,
        payload=next_payload,
        task_uid=task_uid,
        source_object_type=source_object_type,
        source_object_uid=source_object_uid or normalized_node_code,
        node_code=normalized_node_code,
        config_path=str(resolved_node_config_path),
        priority_score=priority_score,
        source=source,
        request_contract=merged_request_contract,
        metadata=next_metadata,
    )


def get_task_request(request_uid: str) -> Dict[str, Any]:
    """读取单个事务请求。"""

    return _get_request(request_uid)


def list_task_requests(task_uid: str | None = None, status: str | None = None) -> List[Dict[str, Any]]:
    """列出事务请求。"""

    if task_uid:
        return _list_task_requests(task_uid)
    return _list_requests(status=status)


def list_schedulable_task_requests(
    *,
    limit: int = 20,
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
    executor_uid: str = "",
) -> List[Dict[str, Any]]:
    """列出可调度事务请求。"""

    return _list_schedulable_requests(
        limit=limit,
        statuses=statuses,
        scheduling_policy=scheduling_policy,
        executor_uid=executor_uid,
    )


def acquire_task_request_lease(
    *,
    executor_uid: str,
    request_uid: str | None = None,
    lease_seconds: int = 120,
    resource_fingerprint: str = "",
    access_mode: str = "写",
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """为执行者领取事务请求租约。"""

    return _acquire_request_lease(
        executor_uid=executor_uid,
        request_uid=request_uid,
        lease_seconds=lease_seconds,
        resource_fingerprint=resource_fingerprint,
        access_mode=access_mode,
        statuses=statuses,
        scheduling_policy=scheduling_policy,
    )


def renew_task_request_lease(*, request_uid: str, executor_uid: str, lease_seconds: int = 120) -> bool:
    """续租事务请求。"""

    return _renew_request_lease(
        request_uid=request_uid,
        executor_uid=executor_uid,
        lease_seconds=lease_seconds,
    )


def release_task_request_lease(
    *,
    request_uid: str,
    executor_uid: str,
    lease_status: str = "已释放",
    heartbeat_status: str = "空闲",
) -> bool:
    """释放事务请求租约。"""

    return _release_request_lease(
        request_uid=request_uid,
        executor_uid=executor_uid,
        lease_status=lease_status,
        heartbeat_status=heartbeat_status,
    )


def upsert_task_request_executor_heartbeat(
    *,
    executor_uid: str,
    executor_type: str = "agent",
    current_request_uid: str = "",
    status: str = "空闲",
    metadata: dict[str, Any] | None = None,
) -> None:
    """更新事务请求执行者心跳。"""

    _upsert_executor_heartbeat(
        executor_uid=executor_uid,
        executor_type=executor_type,
        current_request_uid=current_request_uid,
        status=status,
        metadata=metadata,
    )


def _load_json_mapping(file_path: Path) -> dict[str, Any]:
    """读取 JSON/Python 配置并确保为字典。"""

    payload = load_json_or_py(file_path)
    if not isinstance(payload, dict):
        raise ValueError(f"配置根对象必须是字典：{file_path}")
    return payload


def _import_module_with_repo_fallback(module_name: str, *, workspace_root: Path) -> Any:
    """导入模块；若缺少 sibling 仓库安装，则回退注入源码根目录。"""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        pass

    candidate_roots = [
        workspace_root.parent.parent / "autodo-kit",
        Path(__file__).resolve().parents[2] / "autodo-kit",
        workspace_root.parent.parent / "autodo-engine",
        Path(__file__).resolve().parents[2] / "autodo-engine",
    ]
    seen: set[str] = set()
    for root in candidate_roots:
        resolved = str(root.resolve())
        if resolved in seen or not root.exists():
            continue
        seen.add(resolved)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue

    return importlib.import_module(module_name)


def _node_uid_to_code(node_uid: str) -> str:
    """把图节点 UID 归一化为 A010 这类节点编码。"""

    normalized = str(node_uid or "").strip().lower()
    if normalized.startswith("n_"):
        normalized = normalized[2:]
    return normalized.upper()


def _slice_project_nodes(node_sequence: list[str], start_node: str | None, end_node: str | None) -> list[str]:
    """按起止节点切主链片段。"""

    if not node_sequence:
        return []

    start = str(start_node or node_sequence[0]).strip().upper()
    end = str(end_node or node_sequence[-1]).strip().upper()
    if start not in node_sequence:
        raise KeyError(f"start_node 不在主链图中：{start}")
    if end not in node_sequence:
        raise KeyError(f"end_node 不在主链图中：{end}")

    start_index = node_sequence.index(start)
    end_index = node_sequence.index(end)
    if start_index > end_index:
        raise ValueError(f"start_node 必须早于 end_node：{start} > {end}")
    return node_sequence[start_index : end_index + 1]


def _normalize_ea_auto_audit_mode(mode_text: str | None) -> str:
    """归一化 EA 自动审计模式。"""

    text = str(mode_text or "").strip().lower()
    if text in {"on", "true", "1", "enabled", "开启"}:
        return "on"
    if text in {"off", "false", "0", "disabled", "关闭"}:
        return "off"
    return "auto"


def _normalize_ea_auto_audit_policy(policy_text: str | None) -> str:
    """归一化 EA 自动审计策略。"""

    text = str(policy_text or "").strip().lower()
    if text in {"continue", "auto_pass", "pass", "自动放行", "放行", "放行继续"}:
        return "continue"
    if text in {"fail", "failed", "直接失败", "标记失败", "失败"}:
        return "fail"
    return "llm_decide"


def _normalize_ea_auto_audit_fail_action(action_text: str | None) -> str:
    """归一化 EA 自动审计失败动作。"""

    text = str(action_text or "").strip().lower()
    if text in {"continue", "pass", "继续", "继续执行"}:
        return "continue"
    if text in {"blocked", "block", "阻断", "保持阻断"}:
        return "blocked"
    return "fail"


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """从文本中提取首个 JSON 对象。"""

    text = str(raw_text or "").strip()
    if not text:
        return {}

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index >= 0 and end_index > start_index:
        snippet = text[start_index : end_index + 1]
        try:
            payload = json.loads(snippet)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    return {}


def _resolve_ea_auto_audit_options(
    *,
    runtime: dict[str, Any],
    mode: str | None,
    policy: str | None,
    fail_action: str | None,
    model: str | None,
) -> dict[str, Any]:
    """解析主链运行时 EA 自动审计参数。"""

    runtime_mode = runtime.get("ea_auto_audit_mode") or runtime.get("EA自动审计模式")
    normalized_mode = _normalize_ea_auto_audit_mode(mode if mode is not None else str(runtime_mode or ""))

    if normalized_mode == "auto":
        gate_mode_text = str(runtime.get("gate_mode") or runtime.get("闸门模式") or "").strip().lower()
        enabled = gate_mode_text in {"auto_pass", "自动通过", "auto"}
    else:
        enabled = normalized_mode == "on"

    runtime_policy = runtime.get("ea_auto_audit_policy") or runtime.get("EA自动审计策略")
    runtime_fail_action = runtime.get("ea_auto_audit_fail_action") or runtime.get("EA自动审计失败动作")
    runtime_model = runtime.get("ea_auto_audit_model") or runtime.get("EA自动审计模型")

    return {
        "mode": normalized_mode,
        "enabled": bool(enabled),
        "policy": _normalize_ea_auto_audit_policy(policy if policy is not None else str(runtime_policy or "")),
        "fail_action": _normalize_ea_auto_audit_fail_action(
            fail_action if fail_action is not None else str(runtime_fail_action or "")
        ),
        "model": str(model or runtime_model or "").strip(),
    }


def _invoke_ea_auto_audit(
    *,
    context: dict[str, Any],
    blocked_event: dict[str, Any],
    decision_department_uid: str,
    audit_options: dict[str, Any],
) -> dict[str, Any]:
    """调用 EA 自动审计并返回决策动作。"""

    policy = str(audit_options.get("policy") or "llm_decide")
    fail_action = _normalize_ea_auto_audit_fail_action(str(audit_options.get("fail_action") or "fail"))
    if policy in {"continue", "fail"}:
        return {
            "status": "PASS",
            "action": policy,
            "reason": "EA 自动审计按固定策略执行。",
            "selected_model": "",
            "decision_source": "policy",
            "attempts": [],
            "raw_response": "",
        }

    project_config = context.get("project_config") if isinstance(context.get("project_config"), dict) else {}
    runtime = context.get("runtime") if isinstance(context.get("runtime"), dict) else {}
    llm_payload = project_config.get("llm") if isinstance(project_config.get("llm"), dict) else {}

    try:
        department_payload = _get_department(decision_department_uid)
    except Exception:
        department_payload = {}

    model_name = (
        str(audit_options.get("model") or "").strip()
        or str(runtime.get("synthesis_model") or "").strip()
        or str(llm_payload.get("synthesis_model") or "").strip()
        or str(llm_payload.get("review_state_model") or "").strip()
        or str(department_payload.get("llm_model") or "").strip()
        or "qwen-max"
    )
    api_key_file_raw = str(llm_payload.get("aliyun_api_key_file") or llm_payload.get("api_key_file") or "").strip()

    project_config_path = Path(str(context.get("project_config_path") or "")).resolve()
    workspace_root = Path(str(context.get("workspace_root") or Path.cwd())).resolve()
    api_key_file = ""
    if api_key_file_raw:
        try:
            api_key_file = str(resolve_portable_path(api_key_file_raw, base_dir=project_config_path.parent))
        except Exception:
            api_key_file = api_key_file_raw

    system_prompt = (
        "你是 AOE 的 EA 自动审计器。"
        "当事务返回 BLOCKED 时，你必须给出是否继续主链的机器决策。"
        "仅输出 JSON，不要输出任何解释性文本。"
    )
    user_prompt = (
        "请根据以下阻断事件给出自动审计决策。\n"
        "输出 JSON 格式：{\"action\": \"continue|fail|blocked\", \"reason\": \"...\"}\n"
        "阻断事件：\n"
        f"{json.dumps(blocked_event, ensure_ascii=False, indent=2)}"
    )

    try:
        llm_module = _import_module_with_repo_fallback("autodokit.tools.llm_clients", workspace_root=workspace_root)
        invoke_llm = getattr(llm_module, "invoke_aliyun_llm")
        intent_cls = getattr(llm_module, "ModelRoutingIntent", None)

        intent_obj = None
        if callable(intent_cls):
            try:
                intent_obj = intent_cls(
                    task_type="general",
                    quality_tier="high",
                    budget_tier="balanced",
                    risk_level="high",
                    model=model_name,
                    affair_name="EA自动审计",
                )
            except Exception:
                intent_obj = None

        llm_result = invoke_llm(
            prompt=user_prompt,
            system=system_prompt,
            intent=intent_obj,
            max_tokens=512,
            temperature=0.1,
            api_key_file=api_key_file or None,
            config_path=str(project_config_path) if project_config_path.exists() else None,
            affair_name="EA自动审计",
        )
    except Exception as exc:
        return {
            "status": "FAIL",
            "action": fail_action,
            "reason": f"EA 自动审计调用失败：{exc}",
            "selected_model": model_name,
            "decision_source": "llm",
            "attempts": [],
            "raw_response": "",
            "error": str(exc),
        }

    status_text = str(llm_result.get("status") or "").upper()
    response_payload = llm_result.get("response") if isinstance(llm_result.get("response"), dict) else {}
    response_text = str(response_payload.get("text") or "").strip()
    parsed_payload = _extract_json_object(response_text)

    parsed_action = _normalize_ea_auto_audit_fail_action(str(parsed_payload.get("action") or ""))
    if not str(parsed_payload.get("action") or "").strip() and status_text == "PASS":
        parsed_action = "fail"

    if status_text != "PASS":
        parsed_action = fail_action

    reason_text = str(
        parsed_payload.get("reason")
        or parsed_payload.get("explanation")
        or response_text
        or llm_result.get("error")
        or "EA 自动审计未返回有效结论。"
    ).strip()

    return {
        "status": status_text or "FAIL",
        "action": parsed_action,
        "reason": reason_text,
        "selected_model": str(llm_result.get("selected_model") or model_name),
        "decision_source": "llm",
        "attempts": llm_result.get("attempts") if isinstance(llm_result.get("attempts"), list) else [],
        "raw_response": response_text,
        "error": str(llm_result.get("error") or ""),
    }


def _append_ea_auto_audit_decision(
    *,
    task_uid: str,
    node_code: str,
    request_uid: str,
    blocked_event: dict[str, Any],
    audit_result: dict[str, Any],
    decision_department_uid: str,
) -> str:
    """把 EA 自动审计结果写入决策库。"""

    action = str(audit_result.get("action") or "blocked")
    if action == "continue":
        selected_action = TaskAction.CONTINUE
        task_status_after = TaskStatus.RUNNING
    elif action == "fail":
        selected_action = TaskAction.FAIL
        task_status_after = TaskStatus.FAILED
    else:
        selected_action = TaskAction.SUSPEND
        task_status_after = TaskStatus.BLOCKED

    decision_uid = f"ea-auto-audit-{int(time.time() * 1000)}-{str(request_uid or node_code or 'node').lower()}"
    reason_text = str(audit_result.get("reason") or "EA 自动审计")
    reason_code = f"ea_auto_audit_{action}"

    decision_result = DecisionResult(
        decision_uid=decision_uid,
        task_uid=task_uid,
        node_uid=node_code,
        decision_type=DecisionType.STATUS,
        selected_action=selected_action,
        task_status_before=TaskStatus.BLOCKED,
        task_status_after=task_status_after,
        next_node_uid=None,
        reason_code=reason_code,
        reason_text=reason_text,
        decision_actor="ea_auto_audit",
        decision_members=["ea"],
        decision_mode="EA_AUTO",
        evidence=[json.dumps(blocked_event, ensure_ascii=False)],
    )

    packet_payload = {
        "packet_uid": f"packet-{decision_uid}",
        "task_uid": task_uid,
        "node_uid": node_code,
        "decision_type": "status",
        "task_summary": {"task_uid": task_uid, "request_uid": request_uid},
        "node_summary": {"node_code": node_code, "request_uid": request_uid},
        "receipt": blocked_event,
        "candidate_actions": ["continue", "fail", "blocked"],
        "recommended_action": action,
        "rule_hits": ["ea_auto_audit"],
        "decision_members": ["ea"],
        "decision_mode": "EA_AUTO",
        "artifact_refs": [],
        "agent_recommendations": [
            {
                "department_uid": decision_department_uid,
                "selected_model": str(audit_result.get("selected_model") or ""),
                "decision_source": str(audit_result.get("decision_source") or ""),
            }
        ],
        "evidence": [reason_text],
    }

    append_decision(decision_result, packet_payload)
    return decision_uid


def _resolve_project_mainflow_context(project_config_path: str | Path) -> Dict[str, Any]:
    """解析项目主链运行上下文。"""

    resolved_project_config_path = resolve_portable_path(str(project_config_path), base_dir=Path.cwd())
    project_config = _load_json_mapping(resolved_project_config_path)
    runtime = project_config.get("runtime") if isinstance(project_config.get("runtime"), dict) else {}
    paths_payload = project_config.get("paths") if isinstance(project_config.get("paths"), dict) else {}

    workspace_root_text = str(project_config.get("workspace_root") or "").strip()
    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=resolved_project_config_path.parent)
        if workspace_root_text
        else resolved_project_config_path.parent
    )
    if not workspace_root.exists():
        raise FileNotFoundError(f"workspace_root 不存在：{workspace_root}")

    graph_path_text = str(runtime.get("workflow_graph_path") or "").strip()
    if not graph_path_text:
        raise KeyError("项目配置缺少 runtime.workflow_graph_path")
    graph_path = resolve_portable_path(graph_path_text, base_dir=workspace_root.parent)
    if not graph_path.exists():
        raise FileNotFoundError(f"workflow_graph_path 不存在：{graph_path}")

    registry_path_text = str(paths_payload.get("affair_entry_registry_path") or "").strip()
    if not registry_path_text:
        raise KeyError("项目配置缺少 paths.affair_entry_registry_path")
    registry_path = resolve_portable_path(registry_path_text, base_dir=workspace_root)
    if not registry_path.exists():
        raise FileNotFoundError(f"affair_entry_registry_path 不存在：{registry_path}")

    graph_payload = _load_json_mapping(graph_path)
    registry_payload = _load_json_mapping(registry_path)

    node_sequence: list[str] = []
    for item in graph_payload.get("nodes", []):
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        node_uid = str(item.get("node_uid") or "").strip()
        if not node_uid:
            continue
        node_sequence.append(_node_uid_to_code(node_uid))

    records: dict[str, dict[str, Any]] = {}
    for item in registry_payload.get("records", []):
        if not isinstance(item, dict):
            continue
        node_code = str(item.get("node_code") or "").strip().upper()
        affair_uid = str(item.get("affair_uid") or "").strip()
        raw_config_path = str(item.get("config_path") or "").strip()
        if not node_code:
            continue
        records[node_code] = {
            "node_code": node_code,
            "affair_uid": affair_uid,
            "config_path": str(resolve_portable_path(raw_config_path, base_dir=workspace_root)) if raw_config_path else "",
            "implemented": bool(item.get("implemented", False)),
            "module": str(item.get("module") or "").strip(),
            "callable": str(item.get("callable") or "execute").strip() or "execute",
            "source_py_path": str(item.get("source_py_path") or "").strip(),
        }

    project_payload = project_config.get("project") if isinstance(project_config.get("project"), dict) else {}
    return {
        "project_config_path": resolved_project_config_path,
        "project_config": project_config,
        "runtime": runtime,
        "workspace_root": workspace_root,
        "graph_path": graph_path,
        "registry_path": registry_path,
        "node_sequence": node_sequence,
        "records": records,
        "project_name": str(project_payload.get("project_name") or project_config.get("workflow_name") or workspace_root.name),
        "project_goal": str(project_payload.get("project_goal") or ""),
    }


def validate_project_mainflow(
    *,
    project_config_path: str | Path,
    start_node: str | None = None,
    end_node: str | None = None,
) -> Dict[str, Any]:
    """验证项目主链配置是否可由 AOE 正式运行。"""

    context = _resolve_project_mainflow_context(project_config_path)
    runtime = context["runtime"]
    target_nodes = _slice_project_nodes(
        context["node_sequence"],
        start_node or str(runtime.get("start_node") or "").strip() or None,
        end_node or str(runtime.get("end_node") or "").strip() or None,
    )
    action_routing = runtime.get("user_action_routing") if isinstance(runtime.get("user_action_routing"), dict) else {}
    required_actions = ["execute", "continue", "pause", "retry", "fallback", "stop", "gate_pass"]
    missing_actions = [item for item in required_actions if item not in action_routing]

    reports: list[dict[str, Any]] = []
    missing_registry: list[str] = []
    missing_config: list[str] = []
    unimplemented: list[str] = []
    for node_code in target_nodes:
        record = context["records"].get(node_code)
        if record is None:
            missing_registry.append(node_code)
            reports.append({"node_code": node_code, "ok": False, "reason": "missing_registry"})
            continue

        config_exists = bool(record.get("config_path")) and Path(str(record["config_path"])).exists()
        implemented = bool(record.get("implemented", False))
        if not config_exists:
            missing_config.append(node_code)
        if not implemented:
            unimplemented.append(node_code)
        reports.append(
            {
                "node_code": node_code,
                "ok": config_exists and implemented,
                "implemented": implemented,
                "config_exists": config_exists,
                "affair_uid": str(record.get("affair_uid") or ""),
                "config_path": str(record.get("config_path") or ""),
            }
        )

    return {
        "ok": not missing_registry and not missing_config and not unimplemented and not missing_actions,
        "project_name": context["project_name"],
        "project_goal": context["project_goal"],
        "project_config_path": str(context["project_config_path"]),
        "workspace_root": str(context["workspace_root"]),
        "graph_path": str(context["graph_path"]),
        "registry_path": str(context["registry_path"]),
        "start_node": target_nodes[0] if target_nodes else None,
        "end_node": target_nodes[-1] if target_nodes else None,
        "target_nodes": target_nodes,
        "node_count": len(target_nodes),
        "missing_registry": missing_registry,
        "missing_config": missing_config,
        "unimplemented": unimplemented,
        "missing_actions": missing_actions,
        "reports": reports,
    }


def _run_project_registered_affair(
    *,
    project_config_path: str | Path,
    node_code: str,
    config_path: Path,
    workspace_root: Path,
) -> List[Path] | None:
    """按项目注册表中的 module/callable 回退执行事务。"""

    context = _resolve_project_mainflow_context(project_config_path)
    record = context["records"].get(str(node_code or "").strip().upper()) or {}
    module_name = str(record.get("module") or "").strip()
    callable_name = str(record.get("callable") or "execute").strip() or "execute"
    source_py_path = str(record.get("source_py_path") or "").strip()
    if not module_name and not source_py_path:
        return None

    if module_name:
        module = _import_module_with_repo_fallback(module_name, workspace_root=workspace_root)
    else:
        module = _load_module_from_file(resolve_portable_path(source_py_path, base_dir=workspace_root))

    callable_obj = getattr(module, callable_name)
    try:
        result = callable_obj(config_path, workspace_root=workspace_root)
    except TypeError:
        result = callable_obj(config_path)
    return _normalize_affair_outputs(result)


def run_task_request(
    request_uid: str,
    *,
    simulate: bool = False,
    executor_uid: str = "aoe-default-executor",
    lease_seconds: int = 120,
    scheduling_policy: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """执行单个事务请求并回写请求/任务状态。"""

    request = get_task_request(request_uid)
    current_status = str(request.get("status") or 请求状态_待调度)
    if current_status == 请求状态_已完成:
        raise ValueError(f"事务请求已完成，不能重复执行：{request_uid}")

    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    workspace_root_text = str(payload.get("workspace_root") or metadata.get("workspace_root") or "").strip()
    project_config_path_text = str(payload.get("project_config_path") or metadata.get("project_config_path") or "").strip()
    config_path_text = str(request.get("config_path") or payload.get("node_config_path") or "").strip()
    target_affair_uid = str(request.get("target_affair_uid") or "").strip()
    task_uid = str(request.get("task_uid") or "").strip() or None
    node_code = str(request.get("node_code") or target_affair_uid or "").strip()

    if not target_affair_uid:
        raise ValueError(f"事务请求缺少 target_affair_uid：{request_uid}")
    if not config_path_text:
        raise ValueError(f"事务请求缺少 config_path：{request_uid}")

    config_path = resolve_portable_path(config_path_text, base_dir=Path.cwd())
    if not config_path.exists():
        raise FileNotFoundError(f"事务请求配置不存在：{config_path}")

    workspace_root = (
        resolve_portable_path(workspace_root_text, base_dir=config_path.parent)
        if workspace_root_text
        else config_path.parent.parent
    )
    bootstrap_runtime(str(workspace_root))

    if task_uid:
        task_store.update_task_status(task_uid, TaskStatus.RUNNING)
        task_store.update_task_cursor(task_uid, current_node_uid=node_code, current_affair_uid=target_affair_uid)

    normalized_executor_uid = str(executor_uid or "aoe-default-executor").strip() or "aoe-default-executor"
    lease_bundle = acquire_task_request_lease(
        executor_uid=normalized_executor_uid,
        request_uid=request_uid,
        lease_seconds=lease_seconds,
        resource_fingerprint=f"请求:{request_uid}",
        statuses=[请求状态_待调度, 请求状态_待租约, 请求状态_已租约],
        scheduling_policy=scheduling_policy,
    )
    if lease_bundle is None:
        refreshed = get_task_request(request_uid)
        owner = str(refreshed.get("executor_uid") or "")
        expire_at = str(refreshed.get("lease_expire_at") or "")
        result = {
            "mode": "execute",
            "status": "lease_unavailable",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "executor_uid": normalized_executor_uid,
            "owner_executor_uid": owner,
            "lease_expire_at": expire_at,
        }
        log_store.append_blocked_event("事务请求租约冲突", result)
        return result

    _upsert_executor_heartbeat(
        executor_uid=normalized_executor_uid,
        executor_type="agent",
        current_request_uid=request_uid,
        status="忙碌",
        metadata={"stage": "执行中"},
    )

    _mark_request_running(request_uid)
    log_store.append_runtime_event(
        "事务请求开始",
        {
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "executor_uid": normalized_executor_uid,
            "simulate": bool(simulate),
        },
    )

    if simulate:
        receipt = {
            "result_code": "PASS",
            "message": "模拟执行完成",
            "output_payload": {
                "artifacts": [],
                "affair_uid": target_affair_uid,
                "request_uid": request_uid,
                "node_code": node_code,
                "task_uid": task_uid,
            },
            "executor_meta": {
                "executor_uid": normalized_executor_uid,
                "mode": "simulate",
            },
        }
        result = {
            "mode": "simulate",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "executor_uid": normalized_executor_uid,
            "output_count": 0,
            "outputs": [],
            "result_code": "PASS",
            "message": "模拟执行完成",
            "output_payload": dict(receipt.get("output_payload") or {}),
            "executor_meta": dict(receipt.get("executor_meta") or {}),
            "receipt": receipt,
        }
        _mark_request_ready_for_commit(request_uid, result=result)
        _mark_request_committed(request_uid, result=result)
        _mark_request_completed(request_uid, result=result)
        release_task_request_lease(
            request_uid=request_uid,
            executor_uid=normalized_executor_uid,
            lease_status="已完成",
            heartbeat_status="空闲",
        )
        log_store.append_runtime_event("事务请求完成", result)
        return {
            "status": "simulated",
            **result,
        }

    try:
        try:
            outputs = run_affair(
                target_affair_uid,
                config_path=config_path,
                workspace_root=workspace_root,
            )
        except KeyError:
            if not project_config_path_text:
                raise
            fallback_outputs = _run_project_registered_affair(
                project_config_path=project_config_path_text,
                node_code=node_code,
                config_path=config_path,
                workspace_root=workspace_root,
            )
            if fallback_outputs is None:
                raise
            outputs = fallback_outputs
    except Exception as exc:
        receipt = {
            "result_code": "FAIL",
            "message": f"事务执行异常：{exc}",
            "output_payload": {
                "artifacts": [],
                "affair_uid": target_affair_uid,
                "request_uid": request_uid,
                "node_code": node_code,
                "task_uid": task_uid,
            },
            "executor_meta": {
                "executor_uid": normalized_executor_uid,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        }
        result = {
            "mode": "execute",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "affair_uid": target_affair_uid,
            "executor_uid": normalized_executor_uid,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "result_code": "FAIL",
            "message": f"事务执行异常：{exc}",
            "output_payload": dict(receipt.get("output_payload") or {}),
            "executor_meta": dict(receipt.get("executor_meta") or {}),
            "receipt": receipt,
        }
        _mark_request_failed(request_uid, result=result)
        if task_uid:
            task_store.mark_task_failed(task_uid)
        release_task_request_lease(
            request_uid=request_uid,
            executor_uid=normalized_executor_uid,
            lease_status="已失败",
            heartbeat_status="阻断",
        )
        log_store.append_error_event("事务请求失败", result)
        return {
            "status": "failed",
            **result,
        }

    receipt = _normalize_affair_receipt(
        outputs=outputs,
        affair_uid=target_affair_uid,
        request_uid=request_uid,
        node_code=node_code,
        task_uid=task_uid,
        executor_uid=normalized_executor_uid,
    )
    result_code = str(receipt.get("result_code") or "PASS").upper()
    normalized_message = str(receipt.get("message") or "事务执行完成")
    normalized_output_payload = (
        dict(receipt.get("output_payload") or {})
        if isinstance(receipt.get("output_payload"), dict)
        else {"raw_output_payload": receipt.get("output_payload")}
    )
    normalized_output_payload.setdefault("artifacts", [str(item) for item in outputs])
    normalized_executor_meta = (
        dict(receipt.get("executor_meta") or {})
        if isinstance(receipt.get("executor_meta"), dict)
        else {"raw_executor_meta": receipt.get("executor_meta")}
    )

    result = {
        "mode": "execute",
        "task_uid": task_uid,
        "request_uid": request_uid,
        "node_code": node_code,
        "affair_uid": target_affair_uid,
        "executor_uid": normalized_executor_uid,
        "output_count": len(outputs),
        "outputs": [str(item) for item in outputs],
        "result_code": result_code,
        "message": normalized_message,
        "output_payload": normalized_output_payload,
        "executor_meta": normalized_executor_meta,
        "receipt": {
            "result_code": result_code,
            "message": normalized_message,
            "output_payload": normalized_output_payload,
            "executor_meta": normalized_executor_meta,
        },
    }

    if result_code == "PASS":
        _mark_request_ready_for_commit(request_uid, result=result)
        _mark_request_committed(request_uid, result=result)
        _mark_request_completed(request_uid, result=result)
        release_task_request_lease(
            request_uid=request_uid,
            executor_uid=normalized_executor_uid,
            lease_status="已完成",
            heartbeat_status="空闲",
        )
        log_store.append_runtime_event("事务请求完成", result)
        return {
            "status": "completed",
            **result,
        }

    if result_code == "BLOCKED":
        _mark_request_blocked(request_uid, result=result)
        if task_uid:
            task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
        release_task_request_lease(
            request_uid=request_uid,
            executor_uid=normalized_executor_uid,
            lease_status="已释放",
            heartbeat_status="阻断",
        )
        log_store.append_blocked_event("事务请求阻断", result)
        return {
            "status": "blocked",
            **result,
        }

    _mark_request_failed(request_uid, result=result)
    if task_uid:
        task_store.mark_task_failed(task_uid)
    release_task_request_lease(
        request_uid=request_uid,
        executor_uid=normalized_executor_uid,
        lease_status="已失败",
        heartbeat_status="阻断",
    )
    log_store.append_error_event("事务请求失败", result)
    return {
        "status": "failed",
        **result,
    }


def run_task_requests(
    task_uid: str,
    *,
    max_requests: int = 100,
    simulate: bool = False,
    executor_uid: str = "aoe-default-executor",
    lease_seconds: int = 120,
    scheduling_policy: dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """消费任务下待调度的事务请求。"""

    requests = [
        item
        for item in list_task_requests(task_uid=task_uid)
        if str(item.get("status") or "") in {请求状态_待调度, 请求状态_待租约, 请求状态_已租约}
    ]
    results: list[dict[str, Any]] = []
    for request in requests[: max(0, int(max_requests)) or 0]:
        result = run_task_request(
            str(request.get("request_uid") or ""),
            simulate=simulate,
            executor_uid=executor_uid,
            lease_seconds=lease_seconds,
            scheduling_policy=scheduling_policy,
        )
        results.append(result)
        if result.get("status") not in {"completed", "simulated", "lease_unavailable"}:
            break

    if not results:
        return results

    refreshed = list_task_requests(task_uid=task_uid)
    statuses = {str(item.get("status") or "") for item in refreshed}
    if statuses and statuses <= {请求状态_已完成}:
        task_store.mark_task_completed(task_uid)
    elif 请求状态_已失败 in statuses:
        task_store.mark_task_failed(task_uid)
    elif 请求状态_已阻断 in statuses:
        task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
    return results


def run_scheduler_cycle(
    *,
    max_requests: int = 20,
    simulate: bool = False,
    executor_uid: str = "aoe-default-executor",
    lease_seconds: int = 120,
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """按全局可调度队列执行一轮调度。

    Args:
        max_requests: 最多消费请求数。
        simulate: 是否仅模拟执行。
        executor_uid: 执行者 UID。
        lease_seconds: 租约秒数。
        statuses: 候选状态集合。
        scheduling_policy: 调度评分策略。

    Returns:
        本轮调度执行结果列表。
    """

    limit = max(0, int(max_requests or 0))
    if limit <= 0:
        return []

    normalized_statuses = statuses or [请求状态_待调度, 请求状态_待租约, 请求状态_已租约]
    events: list[dict[str, Any]] = []

    for _ in range(limit):
        candidates = list_schedulable_task_requests(
            limit=1,
            statuses=normalized_statuses,
            scheduling_policy=scheduling_policy,
            executor_uid=executor_uid,
        )
        if not candidates:
            break

        request_uid = str(candidates[0].get("request_uid") or "")
        if not request_uid:
            break

        result = run_task_request(
            request_uid,
            simulate=simulate,
            executor_uid=executor_uid,
            lease_seconds=lease_seconds,
            scheduling_policy=scheduling_policy,
        )
        events.append(result)

        if str(result.get("status") or "") not in {"completed", "simulated", "lease_unavailable"}:
            break

    return events


def run_aoe_control_loop(
    *,
    max_cycles: int = 1,
    max_requests_per_cycle: int = 20,
    simulate: bool = False,
    executor_uid: str = "aoe-default-executor",
    lease_seconds: int = 120,
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
    stop_when_idle: bool = False,
    max_idle_cycles: int = 3,
    idle_sleep_seconds: float = 1.0,
) -> Dict[str, Any]:
    """运行 AOE 简单任务模式控制循环。

    Args:
        max_cycles: 最多执行拍次。
        max_requests_per_cycle: 每拍最多消费请求数。
        simulate: 是否仅模拟执行。
        executor_uid: 执行者 UID。
        lease_seconds: 租约秒数。
        statuses: 候选状态集合。
        scheduling_policy: 调度评分策略。
        stop_when_idle: 是否在持续空闲后提前停止。
        max_idle_cycles: 空闲停机阈值拍数。
        idle_sleep_seconds: 相邻拍次空闲间隔秒数。

    Returns:
        控制循环运行摘要。
    """

    normalized_max_cycles = int(max_cycles or 0)
    if normalized_max_cycles <= 0:
        raise ValueError("max_cycles 必须为正整数")

    normalized_max_requests = max(1, int(max_requests_per_cycle or 1))
    normalized_executor_uid = str(executor_uid or "aoe-default-executor").strip() or "aoe-default-executor"
    normalized_max_idle_cycles = max(1, int(max_idle_cycles or 1))
    normalized_idle_sleep_seconds = max(0.0, float(idle_sleep_seconds or 0.0))

    cycle_reports: list[dict[str, Any]] = []
    total_events = 0
    idle_cycles = 0
    stop_reason = "max_cycles_reached"
    final_status = "completed"

    _upsert_executor_heartbeat(
        executor_uid=normalized_executor_uid,
        executor_type="agent",
        current_request_uid="",
        status="忙碌",
        metadata={
            "stage": "aoe_control_loop",
            "phase": "start",
        },
    )
    log_store.append_runtime_event(
        "AOE控制循环启动",
        {
            "executor_uid": normalized_executor_uid,
            "simulate": bool(simulate),
            "max_cycles": normalized_max_cycles,
            "max_requests_per_cycle": normalized_max_requests,
            "stop_when_idle": bool(stop_when_idle),
            "max_idle_cycles": normalized_max_idle_cycles,
        },
    )

    try:
        for cycle_index in range(1, normalized_max_cycles + 1):
            events = run_scheduler_cycle(
                max_requests=normalized_max_requests,
                simulate=simulate,
                executor_uid=normalized_executor_uid,
                lease_seconds=lease_seconds,
                statuses=statuses,
                scheduling_policy=scheduling_policy,
            )

            event_count = len(events)
            total_events += event_count
            if event_count <= 0:
                idle_cycles += 1
            else:
                idle_cycles = 0

            request_uids = [str(item.get("request_uid") or "") for item in events if str(item.get("request_uid") or "")]
            cycle_reports.append(
                {
                    "cycle_index": cycle_index,
                    "event_count": event_count,
                    "idle_cycles": idle_cycles,
                    "request_uids": request_uids,
                    "events": events,
                }
            )
            log_store.append_runtime_event(
                "AOE控制循环拍次",
                {
                    "executor_uid": normalized_executor_uid,
                    "cycle_index": cycle_index,
                    "event_count": event_count,
                    "idle_cycles": idle_cycles,
                    "request_uids": request_uids,
                },
            )

            if bool(stop_when_idle) and idle_cycles >= normalized_max_idle_cycles:
                stop_reason = "idle_stop"
                final_status = "stopped_idle"
                break

            if cycle_index < normalized_max_cycles and normalized_idle_sleep_seconds > 0:
                time.sleep(normalized_idle_sleep_seconds)
    except Exception:
        final_status = "failed"
        raise
    finally:
        _upsert_executor_heartbeat(
            executor_uid=normalized_executor_uid,
            executor_type="agent",
            current_request_uid="",
            status="空闲",
            metadata={
                "stage": "aoe_control_loop",
                "phase": "end",
                "status": final_status,
                "cycle_count": len(cycle_reports),
                "total_events": total_events,
            },
        )
        log_store.append_runtime_event(
            "AOE控制循环结束",
            {
                "executor_uid": normalized_executor_uid,
                "status": final_status,
                "stop_reason": stop_reason,
                "cycle_count": len(cycle_reports),
                "total_events": total_events,
            },
        )

    return {
        "status": final_status,
        "executor_uid": normalized_executor_uid,
        "simulate": bool(simulate),
        "max_cycles": normalized_max_cycles,
        "max_requests_per_cycle": normalized_max_requests,
        "cycle_count": len(cycle_reports),
        "idle_cycles": idle_cycles,
        "stop_reason": stop_reason,
        "total_events": total_events,
        "cycles": cycle_reports,
    }


def run_project_mainflow(
    *,
    project_config_path: str | Path,
    start_node: str | None = None,
    end_node: str | None = None,
    simulate: bool = False,
    source: str = "项目经理",
    decision_department_uid: str = "dept-default",
    task_management_mode: str = "simple",
    ea_auto_audit_mode: str | None = None,
    ea_auto_audit_policy: str | None = None,
    ea_auto_audit_fail_action: str | None = None,
    ea_auto_audit_model: str | None = None,
) -> Dict[str, Any]:
    """根据项目 config 生成事务请求并正式执行主链片段。"""

    context = _resolve_project_mainflow_context(project_config_path)
    validation = validate_project_mainflow(
        project_config_path=project_config_path,
        start_node=start_node,
        end_node=end_node,
    )
    target_nodes = list(validation.get("target_nodes") or [])
    if not target_nodes:
        raise ValueError("主链切片结果为空，无法运行项目主链")

    workspace_root = Path(str(context["workspace_root"]))
    bootstrap_runtime(str(workspace_root))

    normalized_task_management_mode = str(task_management_mode or "simple").strip().lower()
    if normalized_task_management_mode not in {"simple", "complex"}:
        raise ValueError("task_management_mode 仅支持 simple 或 complex")

    runtime_payload = context["runtime"] if isinstance(context["runtime"], dict) else {}
    ea_auto_audit_options = _resolve_ea_auto_audit_options(
        runtime=runtime_payload,
        mode=ea_auto_audit_mode,
        policy=ea_auto_audit_policy,
        fail_action=ea_auto_audit_fail_action,
        model=ea_auto_audit_model,
    )

    task = create_task(
        title=f"{context['project_name']}主链运行",
        goal_text=str(context.get("project_goal") or "项目主链运行"),
        current_node_uid=target_nodes[0],
    )
    task_uid = str(task.get("task_uid") or task.get("uid_任务") or "")
    task_store.update_task_metadata(
        task_uid,
        {
            "runner_type": "project_mainflow",
            "project_config_path": str(context["project_config_path"]),
            "workspace_root": str(workspace_root),
            "decision_department_uid": decision_department_uid,
            "task_management_mode": normalized_task_management_mode,
            "target_nodes": target_nodes,
            "ea_auto_audit": dict(ea_auto_audit_options),
        },
    )
    task_store.update_task_status(task_uid, TaskStatus.RUNNING)
    log_store.append_runtime_event(
        "项目主链开始",
        {
            "task_uid": task_uid,
            "project_name": context["project_name"],
            "project_config_path": str(context["project_config_path"]),
            "start_node": target_nodes[0],
            "end_node": target_nodes[-1],
            "simulate": bool(simulate),
            "task_management_mode": normalized_task_management_mode,
            "decision_department_uid": decision_department_uid,
            "ea_auto_audit": dict(ea_auto_audit_options),
        },
    )

    events: list[dict[str, Any]] = []
    final_status = "completed"

    def _try_ea_auto_audit(blocked_event: dict[str, Any], *, request_uid: str, node_code: str) -> bool:
        """对 BLOCKED 结果执行 EA 自动审计。"""

        nonlocal final_status

        if not bool(ea_auto_audit_options.get("enabled", False)):
            task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
            final_status = "blocked"
            return False

        audit_result = _invoke_ea_auto_audit(
            context=context,
            blocked_event=blocked_event,
            decision_department_uid=decision_department_uid,
            audit_options=ea_auto_audit_options,
        )
        action = _normalize_ea_auto_audit_fail_action(str(audit_result.get("action") or ""))

        decision_uid = ""
        decision_error = ""
        try:
            decision_uid = _append_ea_auto_audit_decision(
                task_uid=task_uid,
                node_code=node_code,
                request_uid=request_uid,
                blocked_event=blocked_event,
                audit_result=audit_result,
                decision_department_uid=decision_department_uid,
            )
        except Exception as exc:
            decision_error = str(exc)
            log_store.append_error_event(
                "EA自动审计决策落库失败",
                {
                    "task_uid": task_uid,
                    "request_uid": request_uid,
                    "node_code": node_code,
                    "error": decision_error,
                },
            )

        audit_event = {
            "status": "ea_auto_audit",
            "task_uid": task_uid,
            "request_uid": request_uid,
            "node_code": node_code,
            "decision_uid": decision_uid,
            "decision_action": action,
            "decision_error": decision_error,
            "options": dict(ea_auto_audit_options),
            "audit_result": dict(audit_result),
        }
        events.append(audit_event)
        log_store.append_runtime_event("EA自动审计决策", audit_event)

        if request_uid:
            audit_result_payload = {
                "mode": "execute",
                "status": "ea_auto_audit",
                "task_uid": task_uid,
                "request_uid": request_uid,
                "node_code": node_code,
                "decision_uid": decision_uid,
                "decision_action": action,
                "blocked_event": blocked_event,
                "audit_result": audit_result,
            }
            if action == "continue":
                _mark_request_ready_for_commit(request_uid, result=audit_result_payload)
                _mark_request_committed(request_uid, result=audit_result_payload)
                _mark_request_completed(request_uid, result=audit_result_payload)
            elif action == "fail":
                _mark_request_failed(request_uid, result=audit_result_payload)
            else:
                _mark_request_blocked(request_uid, result=audit_result_payload)

        if action == "continue":
            task_store.update_task_status(task_uid, TaskStatus.RUNNING)
            return True

        if action == "fail":
            task_store.mark_task_failed(task_uid)
            final_status = "failed"
            return False

        task_store.update_task_status(task_uid, TaskStatus.BLOCKED)
        final_status = "blocked"
        return False

    for node_code in target_nodes:
        try:
            request = create_task_request_from_project_node(
                project_config_path=str(context["project_config_path"]),
                node_code=node_code,
                task_uid=task_uid,
                source=source,
                metadata={
                    "runner_type": "project_mainflow",
                    "decision_department_uid": decision_department_uid,
                    "task_management_mode": normalized_task_management_mode,
                },
            )
        except Exception as exc:
            blocked_event = {
                "status": "blocked",
                "task_uid": task_uid,
                "node_code": node_code,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            events.append(blocked_event)
            log_store.append_blocked_event("项目主链阻断", blocked_event)
            if _try_ea_auto_audit(blocked_event, request_uid="", node_code=node_code):
                continue
            break

        record = context["records"].get(node_code) or {}
        if not bool(record.get("implemented", False)):
            blocked_result = {
                "task_uid": task_uid,
                "request_uid": str(request.get("request_uid") or ""),
                "node_code": node_code,
                "affair_uid": str(record.get("affair_uid") or request.get("target_affair_uid") or ""),
                "reason": "implemented_false",
            }
            _mark_request_blocked(str(request.get("request_uid") or ""), result=blocked_result)
            events.append({"status": "blocked", **blocked_result})
            log_store.append_blocked_event("事务请求阻断", blocked_result)
            if _try_ea_auto_audit(
                {"status": "blocked", **blocked_result},
                request_uid=str(request.get("request_uid") or ""),
                node_code=node_code,
            ):
                continue
            break

        event = run_task_request(str(request.get("request_uid") or ""), simulate=simulate)
        events.append(event)
        if event.get("status") == "failed":
            final_status = "failed"
            break
        if event.get("status") == "blocked":
            if _try_ea_auto_audit(
                event,
                request_uid=str(event.get("request_uid") or request.get("request_uid") or ""),
                node_code=node_code,
            ):
                continue
            break

    if final_status == "completed":
        task_store.mark_task_completed(task_uid)
    elif final_status == "failed":
        task_store.mark_task_failed(task_uid)
    elif final_status == "blocked":
        task_store.update_task_status(task_uid, TaskStatus.BLOCKED)

    payload = {
        "status": final_status,
        "task_uid": task_uid,
        "project_name": context["project_name"],
        "project_goal": context["project_goal"],
        "project_config_path": str(context["project_config_path"]),
        "workspace_root": str(workspace_root),
        "decision_department_uid": decision_department_uid,
        "ea_auto_audit": dict(ea_auto_audit_options),
        "simulate": bool(simulate),
        "validate": validation,
        "events": events,
        "task": task_store.get_task(task_uid),
        "requests": list_task_requests(task_uid=task_uid),
    }
    log_store.append_runtime_event("项目主链结束", payload)
    return payload


def get_decision_department(department_uid: str = "dept-default") -> Dict[str, Any]:
    """读取决策部门。"""

    return _get_department(department_uid)


def list_decision_departments() -> List[Dict[str, Any]]:
    """列出决策部门。"""

    return _list_departments()


def list_decision_department_members(department_uid: str = "dept-default") -> List[Dict[str, Any]]:
    """列出决策部门成员。"""

    return _list_department_members(department_uid)


def run_task_step(task_uid: str, graph_uid: str) -> DecisionResult:
    """公开的单步运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_step(task_uid=task_uid, graph=graph, run_uid=f"run-{task_uid}")


def run_task_until_wait(task_uid: str, graph_uid: str, max_steps: int = 100) -> list[DecisionResult]:
    """公开的持续运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_until_wait(task_uid=task_uid, graph=graph, max_steps=max_steps)


def run_task_until_terminal(task_uid: str, graph_uid: str, max_steps: int = 100) -> list[DecisionResult]:
    """公开的终止态运行入口。"""

    graph = graph_registry.get_graph(graph_uid)
    return _run_task_until_terminal(task_uid=task_uid, graph=graph, max_steps=max_steps)


def get_task_full_chain_view(task_uid: str) -> Dict[str, Any]:
    """返回任务全链路审计视图。

    Args:
        task_uid: 任务 UID。

    Returns:
        任务全链路审计视图。
    """

    return _build_task_full_chain_view(task_uid)


def get_decision_department_view(task_uid: str | None = None, decision_uid: str | None = None) -> Dict[str, Any]:
    """返回决策部门行为视图。

    Args:
        task_uid: 任务 UID，可选。
        decision_uid: 决策 UID，可选。

    Returns:
        决策部门行为视图。
    """

    return _build_decision_department_view(task_uid=task_uid, decision_uid=decision_uid)


def get_blocked_governance_view(task_uid: str | None = None) -> Dict[str, Any]:
    """返回阻断治理视图。

    Args:
        task_uid: 任务 UID，可选。

    Returns:
        阻断治理聚合视图。
    """

    return _build_blocked_governance_view(task_uid=task_uid)


def refresh_affair_registry(
    工作区根路径: str | Path | None = None,
    严格模式: bool | None = None,
    *,
    workspace_root: str | Path | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """刷新事务数据库并返回同步摘要。

    Args:
        workspace_root: 用户工作区根目录；为空时仅刷新官方库。
        strict: 严格模式，错误即抛异常。

    Returns:
        同步结果摘要。

    Examples:
        >>> result = refresh_affair_registry(workspace_root=None, strict=False)
        >>> isinstance(result.get("stats"), dict)
        True
    """

    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_strict = bool(_resolve_public_argument(("严格模式", 严格模式), ("strict", strict)))
    resolved_workspace = resolve_portable_path(resolved_workspace_root, base_dir=Path.cwd()) if resolved_workspace_root else None
    result = sync_affair_databases(workspace_root=resolved_workspace, strict=resolved_strict)
    return {
        "schema_version": SCHEMA_VERSION,
        "aok_db_path": str(result.aok_db_path),
        "user_db_path": str(result.user_db_path) if str(result.user_db_path) else "",
        "record_count": len(result.records),
        "stats": dict(result.stats),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


def list_runtime_affairs(
    工作区根路径: str | Path | None = None,
    严格模式: bool | None = None,
    *,
    workspace_root: str | Path | None = None,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """列出运行时可用事务记录。

    Args:
        workspace_root: 用户工作区根目录；为空时仅官方事务。
        strict: 严格模式开关。

    Returns:
        事务记录列表。

    Examples:
        >>> items = list_runtime_affairs(workspace_root=None, strict=False)
        >>> isinstance(items, list)
        True
    """

    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_strict = bool(_resolve_public_argument(("严格模式", 严格模式), ("strict", strict)))
    resolved_workspace = resolve_portable_path(resolved_workspace_root, base_dir=Path.cwd()) if resolved_workspace_root else None
    registry = build_runtime_registry(workspace_root=resolved_workspace, strict=resolved_strict)
    return [dict(item) for item in registry.values()]


def check_affair_conflicts(
    工作区根路径: str | Path | None = None,
    *,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    """检查事务同步冲突与告警信息。

    Args:
        workspace_root: 用户工作区根目录；为空时仅检查官方库。

    Returns:
        冲突检查报告。

    Examples:
        >>> report = check_affair_conflicts(workspace_root=None)
        >>> "errors" in report
        True
    """

    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_workspace = resolve_portable_path(resolved_workspace_root, base_dir=Path.cwd()) if resolved_workspace_root else None
    result = sync_affair_databases(workspace_root=resolved_workspace, strict=False)
    return {
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "stats": dict(result.stats),
    }


def get_runtime_store_paths(base_dir: str | Path | None = None) -> Dict[str, str]:
    """返回当前运行时数据库目录与文件路径。

    Args:
        base_dir: 可选运行时根目录；为空时读取当前进程已初始化的运行时根目录。

    Returns:
        包含目录与文件绝对路径的字典。
    """

    dirs = {key: str(value) for key, value in get_runtime_store_dirs(base_dir=base_dir).items()}
    files = {key: str(value) for key, value in get_runtime_store_files(base_dir=base_dir).items()}
    return {
        "runtime_base_dir": dirs["runtime_base_dir"],
        "taskdb_dir": dirs["taskdb"],
        "logdb_dir": dirs["logdb"],
        "decisiondb_dir": dirs["decisiondb"],
        "graph_registry_dir": dirs["graph_registry"],
        "tasks_file": files["tasks"],
        "task_relations_file": files["task_relations"],
        "task_steps_file": files["task_steps"],
        "snapshots_file": files["snapshots"],
        "runtime_events_file": files["runtime_events"],
        "decisions_file": files["decisions"],
        "graphs_file": files["graphs"],
        "types_file": files["types"],
    }


def get_affair_registry_paths(
    工作区根路径: str | Path | None = None,
    *,
    workspace_root: str | Path | None = None,
) -> Dict[str, str]:
    """返回事务管理系统相关路径。

    Args:
        workspace_root: 用户工作区根目录；为空时仅返回官方路径。

    Returns:
        路径字典。
    """

    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_workspace = _normalize_workspace_root(resolved_workspace_root) if resolved_workspace_root is not None else None
    return {key: str(value) for key, value in _get_affair_registry_paths(resolved_workspace).items()}


def list_tools() -> List[str]:
    """返回可用工具名称列表。

    Returns:
        已导出的工具函数名列表。
    """

    tools_module = _load_tools_module()
    exported = getattr(tools_module, "__all__", [])
    if isinstance(exported, list):
        return [str(item) for item in exported]
    return []


def get_tool(tool_name: str) -> Any:
    """按名称获取工具函数。

    Args:
        tool_name: 工具函数名。

    Returns:
        可调用工具函数。

    Raises:
        KeyError: 当工具不存在时抛出。
    """

    key = str(tool_name or "").strip()
    if not key:
        raise KeyError("tool_name 不能为空")

    tools_module = _load_tools_module()
    if not hasattr(tools_module, key):
        raise KeyError(f"工具不存在：{key}")
    return getattr(tools_module, key)


def list_public_tools(exposure: str | None = None, kind: str | None = None) -> List[Dict[str, Any]]:
    """列出 AOK 公开工具（函数名模式）。

    Args:
        exposure: 兼容旧参数。`public-read/public-safe` 映射到 user，`internal` 映射到 developer。
        kind: 兼容旧参数，当前未使用。

    Returns:
        list[dict[str, Any]]: 工具条目列表。

    Raises:
        KeyError: 当工具模块未提供工具清单接口时抛出。
    """

    _ = kind
    tools_module = _load_tools_module()
    list_user = getattr(tools_module, "list_user_tools", None)
    list_developer = getattr(tools_module, "list_developer_tools", None)
    if list_user is None or list_developer is None:
        raise KeyError("工具模块未提供 list_user_tools/list_developer_tools 接口")

    if exposure == "internal":
        scope = "developer"
    elif exposure in {"public-read", "public-safe"}:
        scope = "user"
    else:
        scope = "all"

    rows: list[dict[str, Any]] = []
    if scope in {"user", "all"}:
        for name in list_user():
            rows.append({"tool_name": str(name), "scope": "user"})
    if scope in {"developer", "all"}:
        for name in list_developer():
            rows.append({"tool_name": str(name), "scope": "developer"})
    return rows


def list_capabilities(include_internal: bool = False) -> List[Dict[str, Any]]:
    """列出 public capability 摘要。

    Args:
        include_internal: 是否包含 developer/internal 能力。

    Returns:
        capability 摘要列表。
    """

    tools_module = _load_tools_module_with_attrs("list_capabilities")
    list_capabilities_fn = getattr(tools_module, "list_capabilities")
    return list_capabilities_fn(include_internal=include_internal)


def lint_capabilities() -> Dict[str, Any]:
    """校验 capability manifest/schema/实现一致性。

    Returns:
        lint 摘要字典。
    """

    tools_module = _load_tools_module_with_attrs("lint_public_manifest")
    lint_fn = getattr(tools_module, "lint_public_manifest")
    return lint_fn()


def invoke_capability(
    capability_id: str,
    *,
    payload: Dict[str, Any] | None = None,
    caller_context: Dict[str, Any] | None = None,
    allow_internal: bool = False,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    """统一执行 public capability。

    Args:
        capability_id: 能力标识。
        payload: 输入参数。
        caller_context: 调用上下文。
        allow_internal: 是否允许 developer/internal 能力。
        workspace_root: 工作区根目录，用于审计落盘。

    Returns:
        统一协议结果字典。
    """

    tools_module = _load_tools_module_with_attrs("invoke_capability")
    invoke_fn = getattr(tools_module, "invoke_capability")
    return invoke_fn(
        capability_id,
        payload=payload,
        caller_context=caller_context,
        allow_internal=allow_internal,
        workspace_root=workspace_root,
    )


def invoke_public_tool(
    capability_id: str,
    *,
    payload: Any | None = None,
    caller_context: Dict[str, Any] | None = None,
    allow_internal: bool = False,
) -> Dict[str, Any]:
    """调用 AOK 公开工具（兼容旧接口名）。

    Args:
        capability_id: 工具函数名（兼容旧字段名）。
        payload: 调用参数；支持 `{"args": [...], "kwargs": {...}}`，也兼容直接字典 kwargs。
        caller_context: 调用方上下文，当前仅用于记录来源。
        allow_internal: 兼容旧参数；当前通过 scope 控制是否允许开发者工具。

    Returns:
        dict[str, Any]: 调用结果。

    Raises:
        KeyError: 当工具模块未提供工具调用接口时抛出。
    """

    target = str(capability_id or "").strip()
    if not target:
        raise ValueError("capability_id 不能为空")

    context = dict(caller_context or {})
    context.setdefault("caller_source", "autodoengine.api")

    if payload is None:
        normalized_payload: dict[str, Any] = {}
    elif isinstance(payload, dict):
        raw_args = payload.get("args", None)
        raw_kwargs = payload.get("kwargs", None)
        if raw_args is None and raw_kwargs is None:
            normalized_payload = dict(payload)
        else:
            if raw_args:
                raise ValueError("invoke_public_tool 已切换到 capability 模式，不再支持 args")
            normalized_payload = dict(raw_kwargs or {})
    else:
        raise ValueError("invoke_public_tool 的 payload 必须是对象")

    return invoke_capability(
        target,
        payload=normalized_payload,
        caller_context=context,
        allow_internal=allow_internal,
        workspace_root=normalized_payload.get("workspace_root"),
    )


def prepare_affair_config(
    *,
    配置: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None,
    工作区根路径: str | Path | None = None,
    workspace_root: str | Path | None = None,
) -> Dict[str, Any]:
    """预处理事务配置路径。

    Args:
        config: 原始配置字典。
        workspace_root: 工作区根目录。

    Returns:
        路径已绝对化后的配置字典。
    """

    resolved_config = _resolve_public_argument(("配置", 配置), ("config", config), required=True)
    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root), required=True)
    workspace = _normalize_workspace_root(resolved_workspace_root)
    normalized = dict(resolved_config or {})
    normalized.setdefault("_workspace_root", str(workspace))

    try:
        aok_module = importlib.import_module("autodokit")
        aok_prepare_affair_config = getattr(aok_module, "prepare_affair_config", None)
        if callable(aok_prepare_affair_config):
            resolved = dict(aok_prepare_affair_config(config=normalized, workspace_root=workspace))
            resolved.setdefault(
                "_path_preprocess_summary",
                {
                    "processor": "autodokit.prepare_affair_config",
                    "workspace_root": str(workspace),
                },
            )
            return resolved
    except Exception:
        pass

    resolved, audit = resolve_paths_to_absolute_with_audit(normalized, workspace_root=workspace)
    resolved["_path_preprocess_summary"] = audit
    return resolved


def import_affair_module(
    事务唯一标识: str | None = None,
    *,
    affair_uid: str | None = None,
    工作区根路径: str | Path | None = None,
    workspace_root: str | Path | None = None,
    严格模式: bool | None = None,
    strict: bool = False,
) -> Any:
    """按事务 UID 导入事务模块。

    Args:
        affair_uid: 事务 UID。
        workspace_root: 工作区根目录。
        strict: 严格模式。

    Returns:
        已导入的 Python 模块对象。
    """

    resolved_affair_uid = str(
        _resolve_public_argument(("事务唯一标识", 事务唯一标识), ("affair_uid", affair_uid), required=True)
        or ""
    ).strip()
    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_strict = bool(_resolve_public_argument(("严格模式", 严格模式), ("strict", strict)))
    workspace = _normalize_workspace_root(resolved_workspace_root)
    registry = build_registry(strict=resolved_strict, workspace_root=workspace)
    runner = resolve_runner(resolved_affair_uid, registry)
    module_name = str(runner.get("module") or "").strip()
    source_py_path = str(runner.get("source_py_path") or "").strip()
    if module_name:
        return importlib.import_module(module_name)
    if source_py_path:
        return _load_module_from_file(source_py_path)
    raise ValueError(f"事务[{resolved_affair_uid}] 缺少可导入入口（runner.module/source_py_path）")


def import_user_affair(
    *,
    源码文件路径: str | Path | None = None,
    source_py_path: str | Path | None = None,
    工作区根路径: str | Path | None = None,
    workspace_root: str | Path | None = None,
    参数模板路径: str | Path | None = None,
    source_params_json_path: str | Path | None = None,
    说明文档路径: str | Path | None = None,
    source_doc_md_path: str | Path | None = None,
    事务名称: str | None = None,
    affair_name: str | None = None,
    严格模式: bool | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """导入用户功能程序为事务三件套并注册到事务管理系统。

    Args:
        source_py_path: 功能程序文件路径。
        workspace_root: 用户工作区根目录。
        source_params_json_path: 参数模板 JSON 路径，可选。
        source_doc_md_path: 说明文档 MD 路径，可选。
        affair_name: 事务名称，可选。
        strict: 严格模式，数据库同步有错误时抛异常。

    Returns:
        导入摘要字典。
    """

    resolved_source_py_path = _resolve_public_argument(("源码文件路径", 源码文件路径), ("source_py_path", source_py_path), required=True)
    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root), required=True)
    resolved_source_params_json_path = _resolve_public_argument(("参数模板路径", 参数模板路径), ("source_params_json_path", source_params_json_path))
    resolved_source_doc_md_path = _resolve_public_argument(("说明文档路径", 说明文档路径), ("source_doc_md_path", source_doc_md_path))
    resolved_affair_name = _resolve_public_argument(("事务名称", 事务名称), ("affair_name", affair_name))
    resolved_strict = bool(_resolve_public_argument(("严格模式", 严格模式), ("strict", strict)))
    workspace = _normalize_workspace_root(resolved_workspace_root)
    result = _import_user_affair(
        workspace_root=workspace,
        source_py_path=resolve_portable_path(str(resolved_source_py_path), base_dir=workspace),
        source_params_json_path=(
            resolve_portable_path(str(resolved_source_params_json_path), base_dir=workspace)
            if resolved_source_params_json_path is not None
            else None
        ),
        source_doc_md_path=(
            resolve_portable_path(str(resolved_source_doc_md_path), base_dir=workspace)
            if resolved_source_doc_md_path is not None
            else None
        ),
        affair_name=resolved_affair_name,
        strict=resolved_strict,
    )

    return {
        "requested_name": result.requested_name,
        "final_name": result.final_name,
        "affair_uid": result.affair_uid,
        "renamed": result.renamed,
        "affair_dir": str(result.affair_dir),
        "source_py_path": str(result.source_py_path),
        "params_json_path": str(result.params_json_path),
        "doc_md_path": str(result.doc_md_path),
        "collision_history": list(result.collision_history),
        "warnings": list(result.warnings),
    }


def run_affair(
    事务唯一标识: str | None = None,
    *,
    affair_uid: str | None = None,
    配置: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None,
    配置路径: str | Path | None = None,
    config_path: str | Path | None = None,
    工作区根路径: str | Path | None = None,
    workspace_root: str | Path | None = None,
    严格模式: bool | None = None,
    strict: bool = False,
    运行器参数: Dict[str, Any] | None = None,
    runner_kwargs: Dict[str, Any] | None = None,
) -> List[Path]:
    """统一事务直调入口（强制经由事务管理系统）。

    Args:
        affair_uid: 事务 UID。
        config: 字典配置（`config_dict` 模式优先）。
        config_path: 配置文件路径（JSON/PY）。
        workspace_root: 工作区根目录。
        strict: 严格模式，存在注册错误时抛异常。
        runner_kwargs: 追加给 runner 的调用参数。

    Returns:
        事务产物路径列表。

    Raises:
        ValueError: 参数非法时抛出。
        KeyError: 事务不存在时抛出。
    """

    uid = str(
        _resolve_public_argument(("事务唯一标识", 事务唯一标识), ("affair_uid", affair_uid), required=True)
        or ""
    ).strip()
    if not uid:
        raise ValueError("affair_uid 不能为空")

    resolved_config = _resolve_public_argument(("配置", 配置), ("config", config))
    resolved_config_path = _resolve_public_argument(("配置路径", 配置路径), ("config_path", config_path))
    resolved_workspace_root = _resolve_public_argument(("工作区根路径", 工作区根路径), ("workspace_root", workspace_root))
    resolved_strict = bool(_resolve_public_argument(("严格模式", 严格模式), ("strict", strict)))
    resolved_runner_kwargs = _resolve_public_argument(("运行器参数", 运行器参数), ("runner_kwargs", runner_kwargs))

    workspace = _normalize_workspace_root(resolved_workspace_root)
    registry = build_registry(strict=resolved_strict, workspace_root=workspace)
    runner = resolve_runner(uid, registry)

    module_name = str(runner.get("module") or "").strip()
    source_py_path = str(runner.get("source_py_path") or "").strip()
    if module_name:
        module = importlib.import_module(module_name)
    elif source_py_path:
        module = _load_module_from_file(source_py_path)
    else:
        raise ValueError(f"事务[{uid}] 缺少可导入入口（runner.module/source_py_path）")
    callable_obj = getattr(module, str(runner["callable"]))

    merged_kwargs: Dict[str, Any] = {}
    if isinstance(runner.get("kwargs"), dict):
        merged_kwargs.update(dict(runner.get("kwargs") or {}))
    if isinstance(resolved_runner_kwargs, dict):
        merged_kwargs.update(resolved_runner_kwargs)

    pass_mode = str(runner["pass_mode"])

    if pass_mode == "config_dict":
        config_dict: Dict[str, Any]
        if resolved_config is not None:
            config_dict = dict(resolved_config)
        elif resolved_config_path is not None:
            path_obj = resolve_portable_path(str(resolved_config_path), base_dir=workspace)
            config_dict = load_json_or_py(path_obj)
        else:
            config_dict = {}

        final_config = prepare_affair_config(配置=config_dict, 工作区根路径=workspace)
        if resolved_config_path is not None:
            resolved_config_path_obj = resolve_portable_path(str(resolved_config_path), base_dir=workspace)
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
                json.dump(final_config, fp, ensure_ascii=False, indent=2)
                resolved_config_path_obj = Path(fp.name)

        try:
            with _runtime_context_scope(workspace_root=workspace, affair_uid=uid, config_path=resolved_config_path_obj):
                result = callable_obj(final_config, **merged_kwargs)
        finally:
            if resolved_config_path is None and resolved_config_path_obj.exists():
                resolved_config_path_obj.unlink(missing_ok=True)
        return _normalize_affair_outputs(result)

    if pass_mode == "config_path":
        if resolved_config_path is not None:
            raw_config_path = resolve_portable_path(str(resolved_config_path), base_dir=workspace)
            raw_config = load_json_or_py(raw_config_path)
            final_config = prepare_affair_config(配置=raw_config, 工作区根路径=workspace)
        elif resolved_config is not None:
            final_config = prepare_affair_config(配置=dict(resolved_config), 工作区根路径=workspace)
        else:
            final_config = prepare_affair_config(配置={}, 工作区根路径=workspace)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(final_config, fp, ensure_ascii=False, indent=2)
            resolved_config_path = Path(fp.name)

        try:
            with _runtime_context_scope(workspace_root=workspace, affair_uid=uid, config_path=resolved_config_path):
                result = callable_obj(str(resolved_config_path), **merged_kwargs)
        finally:
            resolved_config_path.unlink(missing_ok=True)
        return _normalize_affair_outputs(result)

    raise ValueError(f"不支持的 pass_mode：{pass_mode}")

