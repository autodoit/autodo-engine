"""流程图节点模板（节点契约模板）。

目标：把“用户不想手写 workflow.json 的 affair 配置”这个问题工程化。

约定：
- 每个节点模板用于创建节点结构与内容契约；
- 节点内容统一使用 `content_kind/content_ref/content_payload`；
- 业务节点模板默认从 `autodokit/affairs/*/affair.json` 的 `node` 字段构造；
- `subgraph_call` 作为内置系统模板保留，不要求用户维护对应 affair。

注意：本模块不负责执行事务，只负责模板加载与节点实例化。
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from autodoengine.utils.common.affair_sync import default_aok_affairs_root
from autodoengine.utils.affair_registry import scan_affairs

from .models import Node, NodeContent, NodePort, FlowGraphError


@dataclass(frozen=True, slots=True)
class NodeTemplate:
    """节点模板（节点内容统一契约）。

    Attributes:
        id: 节点模板唯一标识（建议与文件名一致）。
        uid: 节点模板 UID（由专门脚本一次性生成并写入模板文件）。
        content_kind: 内容类型（`affair` 或 `subgraph`）。
        content_ref: 内容引用（事务标识或子流程图标识）。
        content_payload: 内容默认配置。
        node_type: 节点类型（UI/可视化分组用）。
        is_leaf: 是否叶子节点。
        is_business_node: 是否业务节点。
        is_graph_node: 是否图节点。
        allow_multi_input_ports: 允许多上游输入的端口名列表。
        input_ports: 输入端口定义映射。
        output_ports: 输出端口定义映射。
        affair: 编译到 `workflow.json.affairs[*]` 的基础配置（默认配置）。

    Notes:
        - `affair` 字段仅在 `content_kind=affair` 时参与编译为 workflow 事务配置。
        - 该模板并不限制同一事务在同一流程图中被实例化多次。
          编译时会用节点 uid 作为工作流中的事务 key，以保证唯一性。
    """

    id: str
    uid: str
    content_kind: str
    content_ref: str
    content_payload: Dict[str, Any]
    node_type: str
    is_leaf: bool
    is_business_node: bool
    is_graph_node: bool
    allow_multi_input_ports: list[str]
    input_ports: Dict[str, NodePort]
    output_ports: Dict[str, NodePort]
    affair: Dict[str, Any]


def _default_affairs_root() -> Path:
    """返回默认事务目录。

    Returns:
        官方事务库中的 `autodokit/affairs` 绝对路径。
    """

    return default_aok_affairs_root()


def _make_template_uid(template_id: str) -> str:
    """根据模板标识生成稳定 UID。

    Args:
        template_id: 模板标识。

    Returns:
        稳定的模板 UID。
    """

    digest = hashlib.sha1(template_id.encode("utf-8")).hexdigest()[:12]
    return f"node-tpl-{digest}"


def _build_subgraph_template() -> NodeTemplate:
    """构造内置子流程图模板。

    Returns:
        `subgraph_call` 模板对象。
    """

    return NodeTemplate(
        id="subgraph_call",
        uid="node-tpl-subgraph-call-20260304",
        content_kind="subgraph",
        content_ref="subgraph_inline_child",
        content_payload={"entry": "start"},
        node_type="subgraph",
        is_leaf=False,
        is_business_node=False,
        is_graph_node=True,
        allow_multi_input_ports=[],
        input_ports={"in": NodePort(name="in", data_type="any")},
        output_ports={"out": NodePort(name="out", data_type="any")},
        affair={},
    )


def _coerce_ports(
    raw_ports: Mapping[str, Any],
    *,
    manifest_path: Path,
    field_name: str,
) -> Dict[str, NodePort]:
    """把原始端口映射转换为 `NodePort`。

    Args:
        raw_ports: 原始端口映射。
        manifest_path: 清单路径。
        field_name: 字段名。

    Returns:
        端口映射。

    Raises:
        FlowGraphError: 端口结构非法时抛出。
    """

    ports: Dict[str, NodePort] = {}
    for key, value in raw_ports.items():
        if not isinstance(value, Mapping):
            raise FlowGraphError(f"节点字段 {field_name} 必须是对象映射：{manifest_path}")
        ports[str(key)] = NodePort(**dict(value))
    return ports


def _load_affair_template_from_manifest(manifest_path: Path) -> NodeTemplate | None:
    """从单个 `affair.json` 构造节点模板。

    Args:
        manifest_path: `affair.json` 路径。

    Returns:
        NodeTemplate；若该事务未声明 `node` 字段，则返回 `None`。

    Raises:
        FlowGraphError: 节点字段非法时抛出。
    """

    data = _read_json(manifest_path)
    affair_name = str(data.get("name") or manifest_path.parent.name).strip()
    raw_node = data.get("node")
    if raw_node is None:
        return None
    if not isinstance(raw_node, Mapping):
        raise FlowGraphError(f"事务 node 字段必须是对象：{manifest_path}")

    node_meta = dict(raw_node)
    template_id = affair_name
    template_uid = str(node_meta.get("uid") or "").strip() or _make_template_uid(template_id)
    node_type = str(node_meta.get("node_type") or "").strip()
    if not node_type:
        raise FlowGraphError(f"事务 node.node_type 不能为空：{manifest_path}")

    content_kind = str(node_meta.get("content_kind") or "affair").strip() or "affair"
    if content_kind != "affair":
        raise FlowGraphError(f"事务 node.content_kind 当前仅支持 affair：{manifest_path}")
    content_ref = str(node_meta.get("content_ref") or affair_name).strip() or affair_name

    raw_payload = node_meta.get("payload_defaults") or {}
    if not isinstance(raw_payload, Mapping):
        raise FlowGraphError(f"事务 node.payload_defaults 必须是对象：{manifest_path}")

    raw_inputs = node_meta.get("inputs") or {}
    raw_outputs = node_meta.get("outputs") or {}
    if not isinstance(raw_inputs, Mapping) or not isinstance(raw_outputs, Mapping):
        raise FlowGraphError(f"事务 node.inputs/outputs 必须是对象：{manifest_path}")

    allow_multi_input_ports_raw = node_meta.get("allow_multi_input_ports") or []
    if not isinstance(allow_multi_input_ports_raw, list):
        raise FlowGraphError(f"事务 node.allow_multi_input_ports 必须是列表：{manifest_path}")

    affair_type = str(node_meta.get("affair_type") or "").strip()
    if not affair_type:
        raise FlowGraphError(f"事务 node.affair_type 不能为空：{manifest_path}")

    base_config = node_meta.get("config") or {}
    if not isinstance(base_config, Mapping):
        raise FlowGraphError(f"事务 node.config 必须是对象：{manifest_path}")

    return NodeTemplate(
        id=template_id,
        uid=template_uid,
        content_kind=content_kind,
        content_ref=content_ref,
        content_payload=dict(raw_payload),
        node_type=node_type,
        is_leaf=bool(node_meta.get("is_leaf", False)),
        is_business_node=bool(node_meta.get("is_business", True)),
        is_graph_node=bool(node_meta.get("is_graph", False)),
        allow_multi_input_ports=[
            str(item).strip() for item in allow_multi_input_ports_raw if str(item).strip()
        ],
        input_ports=_coerce_ports(raw_inputs, manifest_path=manifest_path, field_name="inputs"),
        output_ports=_coerce_ports(raw_outputs, manifest_path=manifest_path, field_name="outputs"),
        affair={"type": affair_type, "config": dict(base_config)},
    )


def _read_json(path: Path) -> Dict[str, Any]:
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        JSON 对象字典。

    Raises:
        FlowGraphError: 文件不存在或 JSON 非法。
    """

    if not path.exists():
        raise FlowGraphError(f"节点模板文件不存在：{path}")
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else {}
    except Exception as exc:
        raise FlowGraphError(f"节点模板 JSON 解析失败：{path}：{exc}") from exc


def load_node_template(path: str | Path) -> NodeTemplate:
    """加载单个节点模板。

    Args:
        path: 模板文件路径。

    Returns:
        NodeTemplate 对象。

    Raises:
        FlowGraphError: 模板缺少关键字段或结构非法。
    """

    template_path = Path(path).resolve()

    if template_path.name == "affair.json":
        template = _load_affair_template_from_manifest(template_path)
        if template is None:
            raise FlowGraphError(f"事务未声明 node 字段，无法构造模板：{template_path}")
        return template

    data = _read_json(template_path)
    template_id = str(data.get("id") or data.get("template_id") or template_path.stem).strip()
    template_uid = str(data.get("uid") or "").strip()
    node_type = str(data.get("node_type") or "").strip()
    is_leaf = bool(data.get("is_leaf", False))
    is_business_node = bool(data.get("is_business_node", True))
    is_graph_node = bool(data.get("is_graph_node", False))
    allow_multi_input_ports_raw = data.get("allow_multi_input_ports") or []
    if not isinstance(allow_multi_input_ports_raw, list):
        raise FlowGraphError(f"节点模板 allow_multi_input_ports 必须是列表：{template_path}")
    allow_multi_input_ports = [str(x).strip() for x in allow_multi_input_ports_raw if str(x).strip()]

    if not template_id:
        raise FlowGraphError(f"节点模板 id 不能为空：{template_path}")
    if not template_uid:
        raise FlowGraphError(f"节点模板 uid 不能为空：{template_path}")
    if not node_type:
        raise FlowGraphError(f"节点模板 node_type 不能为空：{template_path}")
    if not is_business_node and not is_graph_node:
        raise FlowGraphError(f"节点模板必须至少属于一种类型（业务或图）：{template_path}")

    raw_content = data.get("content")
    if not isinstance(raw_content, Mapping):
        raise FlowGraphError(f"节点模板必须提供 content 对象：{template_path}")

    content_kind = str(raw_content.get("content_kind") or "").strip()
    content_ref = str(raw_content.get("content_ref") or "").strip()
    content_payload = raw_content.get("content_payload")

    if content_payload is None:
        content_payload = {}
    if not isinstance(content_payload, Mapping):
        raise FlowGraphError(f"节点模板 content_payload 必须是对象：{template_path}")

    if content_kind not in {"affair", "subgraph"}:
        raise FlowGraphError(
            f"节点模板 content_kind 非法（仅支持 affair/subgraph）：{template_path}"
        )
    if not content_ref:
        raise FlowGraphError(f"节点模板 content_ref 不能为空：{template_path}")

    raw_in = data.get("input_ports") or {}
    raw_out = data.get("output_ports") or {}
    if not isinstance(raw_in, Mapping) or not isinstance(raw_out, Mapping):
        raise FlowGraphError(f"节点模板端口定义必须是对象：{template_path}")

    input_ports = {str(k): NodePort(**v) for k, v in raw_in.items()}
    output_ports = {str(k): NodePort(**v) for k, v in raw_out.items()}

    affair = data.get("affair") or {}
    if not isinstance(affair, dict):
        raise FlowGraphError(f"节点模板 affair 字段必须是对象：{template_path}")

    return NodeTemplate(
        id=template_id,
        uid=template_uid,
        content_kind=content_kind,
        content_ref=content_ref,
        content_payload=dict(content_payload),
        node_type=node_type,
        is_leaf=is_leaf,
        is_business_node=is_business_node,
        is_graph_node=is_graph_node,
        allow_multi_input_ports=allow_multi_input_ports,
        input_ports=input_ports,
        output_ports=output_ports,
        affair=dict(affair),
    )


def load_node_templates(templates_dir: str | Path | None = None) -> Dict[str, NodeTemplate]:
    """加载全部节点模板。

    默认行为：
    - 从 `autodokit/affairs/*/affair.json` 的 `node` 字段构造业务/图节点模板；
    - 追加内置 `subgraph_call` 模板。

    Args:
        templates_dir: 兼容旧签名保留，当前不再要求用户维护模板目录。

    Returns:
        以模板 `id` 为键的模板字典。

    Raises:
        FlowGraphError: 模板重复或节点字段非法。
    """

    _ = templates_dir
    templates: Dict[str, NodeTemplate] = {"subgraph_call": _build_subgraph_template()}

    for manifest_path in scan_affairs(_default_affairs_root()):
        tmpl = _load_affair_template_from_manifest(manifest_path)
        if tmpl is None:
            continue
        if tmpl.id in templates:
            raise FlowGraphError(f"节点模板 id 重复：{tmpl.id}")
        templates[tmpl.id] = tmpl

    return templates


def create_node_from_template(
    template: NodeTemplate,
    *,
    node_uid: str,
    payload: Dict[str, Any] | None = None,
) -> Node:
    """根据模板创建节点实例。

    Args:
        template: 节点模板。
        node_uid: 新节点 uid。
        payload: 节点 payload（用于覆盖默认事务配置的部分字段）。

    Returns:
        Node 对象。
    """

    safe_payload = dict(template.content_payload or {})
    safe_payload.update(dict(payload or {}))

    content = NodeContent.from_mapping(
        {
            "content_kind": template.content_kind,
            "content_ref": template.content_ref,
            "content_payload": safe_payload,
        }
    )

    return Node(
        uid=node_uid,
        node_type=template.node_type,
        is_leaf=template.is_leaf,
        is_business_node=template.is_business_node,
        is_graph_node=template.is_graph_node,
        allow_multi_input_ports=list(template.allow_multi_input_ports),
        input_ports=dict(template.input_ports),
        output_ports=dict(template.output_ports),
        content=content,
    )


