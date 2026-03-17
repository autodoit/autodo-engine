"""AOF（Auto Operation Flow）解析与编译辅助。

本模块提供以下能力：
- 解析 Mermaid 风格的流程图文本（AOF 文本段）为 `FlowGraph`；
- 从 Markdown 中提取 `aof` 或 `mermaid` 代码块；
- 生成可读的中间 Python 程序（用于审计与调试）。

当前支持语法（兼容最小语法并扩展）：
- 方向声明：`flowchart TD` / `graph LR`（可选）；
- 连线：`A --> B`；
- 条件边：`A -->|true| B`；
- 节点写法：
    - `节点ID[事务名]`（推荐）；
    - `节点ID[affair:事务名]`（S3 推荐，显式事务节点）；
    - `节点ID[subgraph:模板ID]`（S3 推荐，显式子流程图节点）；
    - `节点ID`（节点ID 同时作为事务名）；
    - `节点ID<节点类型>[事务名]`（新增，支持显式节点类型声明）；
- 容器：`subgraph 容器ID[图节点_container] ... end`（支持嵌套）。

说明：
- 连线仅表达依赖关系，不做端口数据自动注入；
- 端口名由节点模板自动推断（上游首个输出端口 -> 下游首个输入端口）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .models import Edge, FlowGraphError, Node, NodeContent, NodeContentV2, NodePort
from .templates import NodeTemplate, create_node_from_template
from .workflow import FlowGraph


@dataclass(slots=True, frozen=True)
class AofNodeToken:
    """AOF 节点 token 解析结果。

    Attributes:
        node_uid: 节点 uid。
        template_key: 节点模板查找键。
        declared_content_kind: 显式声明的内容类型。
        declared_node_type: 显式声明的节点类型。
    """

    node_uid: str
    template_key: str
    declared_content_kind: str | None = None
    declared_node_type: str | None = None


@dataclass(slots=True, frozen=True)
class AofEdgeSpec:
    """AOF 连线解析结果。

    Attributes:
        source: 源节点 token。
        target: 目标节点 token。
        condition_label: 条件边标签。
    """

    source: AofNodeToken
    target: AofNodeToken
    condition_label: str | None = None


@dataclass(slots=True, frozen=True)
class AofStatement:
    """AOF 有效语句。

    Attributes:
        line: 语句正文。
        container_path: 语句所在容器路径。
    """

    line: str
    container_path: Tuple[str, ...]


def _iter_effective_statements(text: str) -> Iterable[AofStatement]:
    """按行迭代有效语句并记录容器路径。

    Args:
        text: AOF 原始文本。

    Yields:
        AofStatement：去掉注释和空白后的语句及其容器路径。
    """

    container_stack: List[str] = []
    auto_subgraph_seq = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%%"):
            continue
        if line.startswith("flowchart") or line.startswith("graph"):
            continue
        if line.startswith("classDef") or line.startswith("style") or line.startswith("linkStyle"):
            continue

        if line.lower().startswith("subgraph"):
            auto_subgraph_seq += 1
            subgraph_id = _parse_subgraph_id(line=line, auto_seq=auto_subgraph_seq)
            container_stack.append(subgraph_id)
            continue

        if line.lower() == "end":
            if container_stack:
                container_stack.pop()
            continue

        yield AofStatement(line=line, container_path=tuple(container_stack))


def _parse_subgraph_id(*, line: str, auto_seq: int) -> str:
    """解析 subgraph 声明中的容器 ID。

    支持：
    - `subgraph 容器ID[图节点_container]`
    - `subgraph 容器ID`
    - `subgraph [图节点_container]`（自动生成容器 ID）

    Args:
        line: subgraph 原始语句。
        auto_seq: 自动编号。

    Returns:
        容器 ID。
    """

    rest = line[len("subgraph") :].strip()
    if not rest:
        return f"container_auto_{auto_seq}"

    if "[" in rest and rest.endswith("]"):
        left, _ = rest.split("[", 1)
        candidate = left.strip()
        if candidate:
            return candidate
        return f"container_auto_{auto_seq}"

    return rest.strip() or f"container_auto_{auto_seq}"


def _parse_node_token(token: str) -> AofNodeToken:
    """解析节点 token。

    支持：
    - `node_id[label]`
    - `node_id<node_type>[label]`
    - `node_id<node_type>`
    - `node_id`

    Args:
        token: 节点 token。

    Returns:
        AofNodeToken。
    """

    def _parse_declared_kind_and_key(raw_label: str) -> Tuple[str | None, str]:
        """解析 label 中声明的内容类型与模板键。

        支持：
        - `affair:事务名`
        - `subgraph:模板ID`

        未声明类型时，返回 `(None, 原值)`。
        """

        label = str(raw_label or "").strip()
        if ":" not in label:
            return None, label
        kind_raw, key_raw = label.split(":", 1)
        kind = kind_raw.strip().lower()
        key = key_raw.strip()
        if kind in {"affair", "subgraph"} and key:
            return kind, key
        return None, label

    text = token.strip()
    if not text:
        raise FlowGraphError("AOF 节点 token 不能为空。")

    typed_with_label = re.match(r"^(?P<uid>[^<\[\]]+?)<(?P<node_type>[A-Za-z_][\w-]*)>\[(?P<label>.+)\]$", text)
    if typed_with_label:
        node_uid = str(typed_with_label.group("uid") or "").strip()
        declared_node_type = str(typed_with_label.group("node_type") or "").strip()
        raw_label = str(typed_with_label.group("label") or "").strip()
        declared_content_kind, template_key = _parse_declared_kind_and_key(raw_label)
        if not node_uid:
            raise FlowGraphError(f"AOF 节点 ID 不能为空：{token}")
        if not template_key:
            raise FlowGraphError(f"AOF 节点模板键不能为空：{token}")
        return AofNodeToken(
            node_uid=node_uid,
            template_key=template_key,
            declared_content_kind=declared_content_kind,
            declared_node_type=declared_node_type,
        )

    typed_without_label = re.match(r"^(?P<uid>[^<\[\]]+?)<(?P<node_type>[A-Za-z_][\w-]*)>$", text)
    if typed_without_label:
        node_uid = str(typed_without_label.group("uid") or "").strip()
        declared_node_type = str(typed_without_label.group("node_type") or "").strip()
        if not node_uid:
            raise FlowGraphError(f"AOF 节点 ID 不能为空：{token}")
        return AofNodeToken(
            node_uid=node_uid,
            template_key=node_uid,
            declared_node_type=declared_node_type,
        )

    if "[" in text and text.endswith("]"):
        left, right = text.split("[", 1)
        node_uid = left.strip()
        raw_label = right[:-1].strip()
        declared_content_kind, template_key = _parse_declared_kind_and_key(raw_label)
        if not node_uid:
            raise FlowGraphError(f"AOF 节点 ID 不能为空：{token}")
        if not template_key:
            raise FlowGraphError(f"AOF 节点模板键不能为空：{token}")
        return AofNodeToken(
            node_uid=node_uid,
            template_key=template_key,
            declared_content_kind=declared_content_kind,
        )

    # 无 label 时，节点名即事务名。
    return AofNodeToken(node_uid=text, template_key=text)


def _parse_edge_line(line: str) -> AofEdgeSpec:
    """解析一条连线语句。

    Args:
        line: 连线语句，例如 `A --> B`。

    Returns:
        AofEdgeSpec。

    Raises:
        FlowGraphError: 语法不合法时抛出。
    """

    if "-->" not in line:
        raise FlowGraphError(f"AOF 仅支持 '-->' 连线：{line}")

    left_text, right_text = line.split("-->", 1)
    left = left_text.strip()
    right = right_text.strip()

    condition_label: str | None = None

    # 兼容 Mermaid 的边标签：A -->|label| B
    if right.startswith("|"):
        label_match = re.match(r"^\|([^|]+)\|\s*(.+)$", right)
        if label_match is None:
            raise FlowGraphError(f"AOF 边标签语法非法：{line}")
        condition_label = str(label_match.group(1) or "").strip() or None
        right = str(label_match.group(2) or "").strip()

    if not left or not right:
        raise FlowGraphError(f"AOF 连线两端不能为空：{line}")

    return AofEdgeSpec(
        source=_parse_node_token(left),
        target=_parse_node_token(right),
        condition_label=condition_label,
    )


def _parse_node_declaration_line(line: str) -> AofNodeToken:
    """解析节点声明语句。

    Args:
        line: 节点声明语句。

    Returns:
        AofNodeToken。

    Raises:
        FlowGraphError: 语句非法时抛出。
    """

    if "-->" in line:
        raise FlowGraphError(f"节点声明语句不应包含连线：{line}")
    return _parse_node_token(line)


def _pick_source_port(template: NodeTemplate, *, condition_label: str | None = None) -> str:
    """选择源节点输出端口名。

    Args:
        template: 节点模板。
        condition_label: 条件边标签。

    Returns:
        输出端口名。

    Raises:
        FlowGraphError: 无输出端口时抛出。
    """

    if not template.output_ports:
        raise FlowGraphError(f"事务模板缺少输出端口，无法作为上游：{template.content_ref}")

    if condition_label:
        cond = condition_label.strip()
        if cond in template.output_ports:
            return cond
        cond_lower = cond.lower()
        for port_name in template.output_ports:
            if port_name.lower() == cond_lower:
                return port_name

    return next(iter(template.output_ports.keys()))


def _pick_target_port(template: NodeTemplate, *, condition_label: str | None = None) -> str:
    """选择目标节点输入端口名。

    Args:
        template: 节点模板。
        condition_label: 条件边标签。

    Returns:
        输入端口名。

    Raises:
        FlowGraphError: 无输入端口时抛出。
    """

    if not template.input_ports:
        raise FlowGraphError(f"事务模板缺少输入端口，无法作为下游：{template.content_ref}")

    if condition_label:
        cond = condition_label.strip()
        if cond in template.input_ports:
            return cond
        cond_lower = cond.lower()
        for port_name in template.input_ports:
            if port_name.lower() == cond_lower:
                return port_name

    return next(iter(template.input_ports.keys()))


def parse_aof_to_flow_graph(
    aof_text: str,
    *,
    templates_by_content_ref: Mapping[str, NodeTemplate],
    graph_uid: str,
    payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> FlowGraph:
    """将 AOF 文本解析为流程图对象。

    Args:
        aof_text: AOF 文本段。
        templates_by_content_ref: 事务模板映射（键为 content_ref）。
        graph_uid: 图 ID。
        payloads: 节点 payload 覆盖表，键优先匹配 node_uid，其次匹配模板键。

    Returns:
        解析得到的 `FlowGraph`。

    Raises:
        FlowGraphError: AOF 语法或模板匹配失败。
    """

    graph = FlowGraph(uid=graph_uid)

    templates_by_id = {template.id: template for template in templates_by_content_ref.values()}

    node_template_keys: Dict[str, str] = {}
    node_declared_content_kinds: Dict[str, str] = {}
    node_declared_types: Dict[str, str] = {}
    node_container_paths: Dict[str, Tuple[str, ...]] = {}
    node_templates: Dict[str, NodeTemplate] = {}
    parsed_edges: List[Tuple[str, str, str | None, Tuple[str, ...]]] = []

    def _resolve_template(token: AofNodeToken) -> NodeTemplate:
        """根据 token 解析节点模板。"""

        if token.declared_content_kind == "affair":
            template = templates_by_content_ref.get(token.template_key)
            if template is None:
                raise FlowGraphError(
                    f"AOF 事务节点[{token.node_uid}] 未找到事务模板：{token.template_key}。"
                    "事务节点建议写法：节点ID[affair:事务名]。"
                )
            return template

        if token.declared_content_kind == "subgraph":
            template = templates_by_id.get(token.template_key)
            if template is None:
                raise FlowGraphError(
                    f"AOF 子流程图节点[{token.node_uid}] 未找到模板 ID：{token.template_key}。"
                    "子流程图节点建议写法：节点ID[subgraph:模板ID]。"
                )
            return template

        template = templates_by_content_ref.get(token.template_key)
        if template is not None:
            return template
        template = templates_by_id.get(token.template_key)
        if template is not None:
            return template
        raise FlowGraphError(
            f"AOF 节点[{token.node_uid}] 未找到可用模板：{token.template_key}。"
            "可选写法：节点ID[affair:事务名] 或 节点ID[subgraph:模板ID]。"
        )

    def _register_node(token: AofNodeToken, *, container_path: Tuple[str, ...]) -> None:
        """注册节点解析信息。

        Args:
            token: 节点 token。
            container_path: 所在容器路径。
        """

        existing_template_key = node_template_keys.get(token.node_uid)
        if existing_template_key and existing_template_key != token.template_key:
            # 兼容“先声明节点，再用裸节点 ID 引用”的写法：
            # 若 token 形如 `node_id`（即 template_key == node_uid），则视为引用已有声明。
            if token.template_key == token.node_uid:
                return
            raise FlowGraphError(
                f"节点 {token.node_uid} 被重复定义为不同模板：{existing_template_key} / {token.template_key}"
            )

        resolved_template = _resolve_template(token)
        node_template_keys[token.node_uid] = token.template_key
        node_templates[token.node_uid] = resolved_template

        if token.declared_content_kind:
            expected_kind = token.declared_content_kind
            actual_kind = resolved_template.content_kind
            if expected_kind != actual_kind:
                raise FlowGraphError(
                    f"节点 {token.node_uid} 内容类型声明与模板不一致："
                    f"declared={expected_kind}, template={actual_kind}, template_id={resolved_template.id}。"
                    "事务节点建议写法：节点ID[affair:事务名]；"
                    "子流程图节点建议写法：节点ID[subgraph:模板ID]。"
                )
            existing_kind = node_declared_content_kinds.get(token.node_uid)
            if existing_kind and existing_kind != expected_kind:
                raise FlowGraphError(
                    f"节点 {token.node_uid} 被重复声明为不同内容类型："
                    f"{existing_kind} / {expected_kind}"
                )
            node_declared_content_kinds[token.node_uid] = expected_kind

        if token.declared_node_type:
            existing_declared = node_declared_types.get(token.node_uid)
            if existing_declared and existing_declared != token.declared_node_type:
                raise FlowGraphError(
                    f"节点 {token.node_uid} 被重复声明为不同节点类型："
                    f"{existing_declared} / {token.declared_node_type}"
                )
            node_declared_types[token.node_uid] = token.declared_node_type

        existing_path = node_container_paths.get(token.node_uid)
        if existing_path is None:
            node_container_paths[token.node_uid] = container_path
            return

        if existing_path == container_path:
            return

        if not existing_path and container_path:
            node_container_paths[token.node_uid] = container_path
            return

        if existing_path and not container_path:
            return

        if container_path[: len(existing_path)] == existing_path:
            node_container_paths[token.node_uid] = container_path
            return

        if existing_path[: len(container_path)] == container_path:
            return

        raise FlowGraphError(
            f"节点 {token.node_uid} 同时出现在冲突的容器路径：{existing_path} / {container_path}"
        )

    for statement in _iter_effective_statements(aof_text):
        line = statement.line
        container_path = statement.container_path

        if "-->" in line:
            edge_spec = _parse_edge_line(line)
            _register_node(edge_spec.source, container_path=container_path)
            _register_node(edge_spec.target, container_path=container_path)
            parsed_edges.append(
                (
                    edge_spec.source.node_uid,
                    edge_spec.target.node_uid,
                    edge_spec.condition_label,
                    container_path,
                )
            )
            continue

        node_token = _parse_node_declaration_line(line)
        _register_node(node_token, container_path=container_path)

    node_payloads: Dict[str, Mapping[str, Any]] = dict(payloads or {})

    for node_uid, template_key in node_template_keys.items():
        template = node_templates[node_uid]

        declared_node_type = node_declared_types.get(node_uid)
        if declared_node_type and declared_node_type != template.node_type:
            raise FlowGraphError(
                f"节点 {node_uid} 声明类型与模板类型不一致："
                f"declared={declared_node_type}, template={template.node_type}"
            )

        payload = node_payloads.get(node_uid) or node_payloads.get(template_key) or node_payloads.get(template.id) or {}
        node = create_node_from_template(template, node_uid=node_uid, payload=dict(payload))
        node.graph_meta.update(
            {
                "aof": {
                    "declared_content_kind": node_declared_content_kinds.get(node_uid),
                    "declared_node_type": declared_node_type,
                    "container_path": list(node_container_paths.get(node_uid, tuple())),
                }
            }
        )
        graph.add_node(node)

    edge_seq = 0
    for autodokit_uid, dst_uid, condition_label, container_path in parsed_edges:
        autodokit_template = node_templates[autodokit_uid]
        dst_template = node_templates[dst_uid]
        edge_seq += 1
        graph.add_edge(
            Edge(
                uid=f"edge-{edge_seq}",
                source_node_uid=autodokit_uid,
                source_port_name=_pick_source_port(autodokit_template, condition_label=condition_label),
                target_node_uid=dst_uid,
                target_port_name=_pick_target_port(dst_template, condition_label=condition_label),
                condition_label=condition_label,
                graph_meta={
                    "aof": {
                        "condition_label": condition_label,
                        "container_path": list(container_path),
                    }
                },
            )
        )

    return graph


def extract_aof_block_from_markdown(markdown_text: str) -> str:
    """从 Markdown 中提取首个 AOF 文本块。

    识别顺序：
    1) ```aof
    2) ```mermaid

    Args:
        markdown_text: Markdown 全文。

    Returns:
        代码块内容（去除围栏）。

    Raises:
        FlowGraphError: 找不到可识别代码块时抛出。
    """

    patterns = [
        re.compile(r"```aof\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE),
        re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(markdown_text)
        if match:
            return match.group(1).strip()
    raise FlowGraphError("Markdown 中未找到 `aof` 或 `mermaid` 代码块。")


def load_aof_text(
    *,
    aof_text: str | None,
    aof_md_path: str | None,
    workflow_dir: Path,
) -> str:
    """加载 AOF 文本。

    Args:
        aof_text: workflow.json 内嵌文本。
        aof_md_path: Markdown 文件路径（相对 workflow 目录或绝对路径）。
        workflow_dir: workflow.json 所在目录。

    Returns:
        AOF 文本。

    Raises:
        FlowGraphError: 两种来源都缺失或 md 不存在时抛出。
    """

    if isinstance(aof_text, str) and aof_text.strip():
        return aof_text.strip()

    if isinstance(aof_md_path, str) and aof_md_path.strip():
        md_path = Path(aof_md_path.strip())
        if not md_path.is_absolute():
            md_path = (workflow_dir / md_path).resolve()
        if not md_path.exists():
            raise FlowGraphError(f"AOF Markdown 文件不存在：{md_path}")
        markdown_text = md_path.read_text(encoding="utf-8")
        return extract_aof_block_from_markdown(markdown_text)

    raise FlowGraphError("AOF 配置缺少 `aof_text` 或 `aof_md_path`。")


def write_flow_graph_python_program(
    graph: FlowGraph,
    *,
    output_path: Path,
    templates_dir: Path | None = None,
) -> Path:
    """写出中间 Python 程序。

    该程序用于审计和调试，能够重建当前 `FlowGraph`。

    Args:
        graph: 流程图对象。
        output_path: 输出 .py 路径。
        templates_dir: 兼容旧签名保留，当前未使用。

    Returns:
        写出的绝对路径。
    """

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = templates_dir

    lines: List[str] = []
    lines.append('"""AOF 编译生成的中间流程图程序。"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("from autodoengine.flow_graph import Edge, FlowGraph, Node, NodeContent, NodeContentV2, NodePort")
    lines.append("")
    lines.append("")
    lines.append("def build_graph() -> FlowGraph:")
    lines.append('    """构建由 AOF 解析得到的流程图。"""')
    lines.append(f"    graph = FlowGraph(uid={graph.uid!r})")
    lines.append("")

    for node in graph.nodes.values():
        content_v2 = node.content_v2
        lines.append("    graph.add_node(Node(")
        lines.append(f"        uid={node.uid!r},")
        lines.append(f"        node_type={node.node_type!r},")
        lines.append(f"        is_leaf={node.is_leaf!r},")
        lines.append(f"        is_business_node={node.is_business_node!r},")
        lines.append(f"        is_graph_node={node.is_graph_node!r},")
        lines.append(f"        graph_meta={repr(node.graph_meta)},")
        lines.append(f"        allow_multi_input_ports={repr(node.allow_multi_input_ports)},")
        lines.append("        input_ports={")
        for key, port in node.input_ports.items():
            lines.append(
                f"            {key!r}: NodePort(name={port.name!r}, data_type={port.data_type!r}),"
            )
        lines.append("        },")
        lines.append("        output_ports={")
        for key, port in node.output_ports.items():
            lines.append(
                f"            {key!r}: NodePort(name={port.name!r}, data_type={port.data_type!r}),"
            )
        lines.append("        },")
        lines.append("        content=NodeContent.from_v2(NodeContentV2(")
        lines.append(f"            content_kind={content_v2.content_kind!r},")
        lines.append(f"            content_ref={content_v2.content_ref!r},")
        lines.append(f"            content_payload={json.dumps(content_v2.content_payload, ensure_ascii=False)},")
        lines.append("        )),")
        lines.append("    ))")

    lines.append("")
    for edge in graph.edges.values():
        lines.append(
            "    graph.add_edge(Edge(" 
            f"uid={edge.uid!r}, source_node_uid={edge.source_node_uid!r}, "
            f"source_port_name={edge.source_port_name!r}, target_node_uid={edge.target_node_uid!r}, "
            f"target_port_name={edge.target_port_name!r}, condition_label={edge.condition_label!r}, "
            f"graph_meta={repr(edge.graph_meta)}))"
        )
    lines.append("")
    lines.append("    return graph")
    lines.append("")
    lines.append("")
    lines.append("if __name__ == \"__main__\":")
    lines.append("    print(build_graph().to_dict())")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path

