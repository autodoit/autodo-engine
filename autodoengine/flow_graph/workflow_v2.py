"""节点中心工作流 Schema V2。

本模块定义 nodes/edges/containers 为唯一真源的工作流结构，
并提供从字典到强类型对象的加载与校验能力。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping


class WorkflowV2Error(ValueError):
    """节点中心工作流 V2 异常。"""


@dataclass(slots=True, frozen=True)
class WorkflowNodeContentV2:
    """节点内容结构。

    Args:
        content_kind: 内容类型，支持 `affair` 或 `subgraph`。
        content_ref: 内容引用标识。
        content_payload: 内容参数。

    Raises:
        WorkflowV2Error: 字段非法时抛出。

    Examples:
        >>> WorkflowNodeContentV2(content_kind="affair", content_ref="n_start")
        WorkflowNodeContentV2(content_kind='affair', content_ref='n_start', content_payload={})
    """

    content_kind: str
    content_ref: str
    content_payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """执行节点内容合法性检查。

        Raises:
            WorkflowV2Error: 字段非法时抛出。
        """

        kind = str(self.content_kind or "").strip().lower()
        if kind not in {"affair", "subgraph"}:
            raise WorkflowV2Error(f"content.content_kind 非法：{self.content_kind}")
        if not str(self.content_ref or "").strip():
            raise WorkflowV2Error("content.content_ref 不能为空")


@dataclass(slots=True, frozen=True)
class WorkflowNodeV2:
    """节点结构。

    Args:
        id: 节点业务标识。
        uid: 节点唯一标识。
        node_type: 节点类型。
        container: 所属容器标识。
        content: 节点内容。
        ports: 端口定义。
        policies: 节点策略。

    Raises:
        WorkflowV2Error: 字段非法时抛出。
    """

    id: str
    uid: str
    node_type: str
    container: str
    content: WorkflowNodeContentV2
    ports: Dict[str, Any] = field(default_factory=dict)
    policies: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """执行节点合法性检查。

        Raises:
            WorkflowV2Error: 字段非法时抛出。
        """

        if not str(self.id or "").strip():
            raise WorkflowV2Error("node.id 不能为空")
        if not str(self.uid or "").strip():
            raise WorkflowV2Error("node.uid 不能为空")
        if not str(self.node_type or "").strip():
            raise WorkflowV2Error(f"node[{self.uid}] 的 node_type 不能为空")
        if not str(self.container or "").strip():
            raise WorkflowV2Error(f"node[{self.uid}] 的 container 不能为空")


@dataclass(slots=True, frozen=True)
class WorkflowEdgeV2:
    """连线结构。

    Args:
        uid: 连线唯一标识。
        source_node_uid: 起点节点 uid。
        target_node_uid: 终点节点 uid。
        condition_label: 条件标签。
    """

    uid: str
    source_node_uid: str
    target_node_uid: str
    condition_label: str = ""

    def __post_init__(self) -> None:
        """执行连线合法性检查。

        Raises:
            WorkflowV2Error: 字段非法时抛出。
        """

        if not str(self.uid or "").strip():
            raise WorkflowV2Error("edge.uid 不能为空")
        if not str(self.source_node_uid or "").strip():
            raise WorkflowV2Error(f"edge[{self.uid}] 的 source_node_uid 不能为空")
        if not str(self.target_node_uid or "").strip():
            raise WorkflowV2Error(f"edge[{self.uid}] 的 target_node_uid 不能为空")


@dataclass(slots=True, frozen=True)
class WorkflowContainerV2:
    """容器结构。

    Args:
        id: 容器标识。
        parent: 父容器标识，可为空。
        policies: 容器策略。
    """

    id: str
    parent: str = ""
    policies: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """执行容器合法性检查。

        Raises:
            WorkflowV2Error: 字段非法时抛出。
        """

        if not str(self.id or "").strip():
            raise WorkflowV2Error("container.id 不能为空")


@dataclass(slots=True, frozen=True)
class WorkflowV2:
    """节点中心工作流对象。

    Args:
        workflow_id: 工作流标识。
        workflow_name: 工作流名称。
        nodes: 节点映射。
        edges: 连线列表。
        containers: 容器映射。
    """

    workflow_id: str
    workflow_name: str
    nodes: Dict[str, WorkflowNodeV2]
    edges: List[WorkflowEdgeV2]
    containers: Dict[str, WorkflowContainerV2]


def load_workflow_v2_from_mapping(workflow: Mapping[str, Any]) -> WorkflowV2:
    """从字典加载节点中心工作流。

    Args:
        workflow: workflow.json 字典对象。

    Returns:
        WorkflowV2: 强类型工作流对象。

    Raises:
        WorkflowV2Error: 结构非法时抛出。

    Examples:
        >>> wf = load_workflow_v2_from_mapping({
        ...     "workflow_id": "demo",
        ...     "workflow_name": "demo",
        ...     "nodes": [{"id": "n1", "uid": "n1", "node_type": "start", "container": "root", "content": {"content_kind": "affair", "content_ref": "n1"}}],
        ...     "edges": [],
        ...     "containers": [{"id": "root"}],
        ... })
        >>> wf.workflow_id
        'demo'
    """

    workflow_id = str(workflow.get("workflow_id") or "").strip()
    workflow_name = str(workflow.get("workflow_name") or workflow_id).strip()
    if not workflow_id:
        raise WorkflowV2Error("workflow_id 不能为空")

    raw_nodes = workflow.get("nodes")
    raw_edges = workflow.get("edges")
    raw_containers = workflow.get("containers")

    if not isinstance(raw_nodes, list):
        raise WorkflowV2Error("nodes 必须是列表")
    if not isinstance(raw_edges, list):
        raise WorkflowV2Error("edges 必须是列表")
    if not isinstance(raw_containers, list):
        raise WorkflowV2Error("containers 必须是列表")

    containers: Dict[str, WorkflowContainerV2] = {}
    for raw_container in raw_containers:
        if not isinstance(raw_container, Mapping):
            raise WorkflowV2Error("containers 元素必须是对象")
        container = WorkflowContainerV2(
            id=str(raw_container.get("id") or "").strip(),
            parent=str(raw_container.get("parent") or "").strip(),
            policies=dict(raw_container.get("policies") or {}),
        )
        if container.id in containers:
            raise WorkflowV2Error(f"container.id 重复：{container.id}")
        containers[container.id] = container

    if "root" not in containers:
        raise WorkflowV2Error("containers 必须包含 id=root 的根容器")

    nodes: Dict[str, WorkflowNodeV2] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, Mapping):
            raise WorkflowV2Error("nodes 元素必须是对象")

        raw_content = raw_node.get("content")
        if not isinstance(raw_content, Mapping):
            raise WorkflowV2Error("node.content 必须是对象")

        content = WorkflowNodeContentV2(
            content_kind=str(raw_content.get("content_kind") or "").strip(),
            content_ref=str(raw_content.get("content_ref") or "").strip(),
            content_payload=dict(raw_content.get("content_payload") or {}),
        )

        node = WorkflowNodeV2(
            id=str(raw_node.get("id") or "").strip(),
            uid=str(raw_node.get("uid") or "").strip(),
            node_type=str(raw_node.get("node_type") or "").strip(),
            container=str(raw_node.get("container") or "").strip(),
            content=content,
            ports=dict(raw_node.get("ports") or {}),
            policies=dict(raw_node.get("policies") or {}),
        )
        if node.uid in nodes:
            raise WorkflowV2Error(f"node.uid 重复：{node.uid}")
        if node.container not in containers:
            raise WorkflowV2Error(f"node[{node.uid}] 引用了不存在的 container：{node.container}")
        nodes[node.uid] = node

    edges: List[WorkflowEdgeV2] = []
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            raise WorkflowV2Error("edges 元素必须是对象")
        edge = WorkflowEdgeV2(
            uid=str(raw_edge.get("uid") or "").strip(),
            source_node_uid=str(raw_edge.get("source_node_uid") or "").strip(),
            target_node_uid=str(raw_edge.get("target_node_uid") or "").strip(),
            condition_label=str(raw_edge.get("condition_label") or "").strip(),
        )
        if edge.source_node_uid not in nodes:
            raise WorkflowV2Error(f"edge[{edge.uid}] 的 source 节点不存在：{edge.source_node_uid}")
        if edge.target_node_uid not in nodes:
            raise WorkflowV2Error(f"edge[{edge.uid}] 的 target 节点不存在：{edge.target_node_uid}")
        edges.append(edge)

    return WorkflowV2(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        nodes=nodes,
        edges=edges,
        containers=containers,
    )
