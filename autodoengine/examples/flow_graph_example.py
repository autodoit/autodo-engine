"""流程图最小示例（V2 前端契约）。

演示：用 `Node`/`Edge`/`NodeContent`/`NodePort` 手工搭一张两节点流程图，
并导出为字典。节点内容统一使用 `content_kind/content_ref/content_payload`。
示例事务使用学科无关的占位名（demo_affair_a/b），不引入任何领域术语。
"""

from __future__ import annotations

from autodoengine.flow_graph import Edge, FlowGraph, Node, NodeContent, NodePort


def build_minimal_workflow() -> FlowGraph:
    """构建一个最简流程图示例。

    Returns:
        包含两个节点和一条有向连线的流程图对象。

    Examples:
        >>> wf = build_minimal_workflow()
        >>> len(wf.nodes), len(wf.edges)
        (2, 1)
    """

    workflow = FlowGraph(uid="workflow-demo-001")

    source_node = Node(
        uid="node-source",
        node_type="process",
        is_leaf=False,
        input_ports={},
        output_ports={"result": NodePort(name="result", data_type="text")},
        content=NodeContent(
            content_kind="affair",
            content_ref="demo_affair_a",
            content_payload={"input": "data/original", "output": "data/output"},
        ),
    )

    target_node = Node(
        uid="node-target",
        node_type="process",
        is_leaf=True,
        input_ports={"in": NodePort(name="in", data_type="text")},
        output_ports={},
        content=NodeContent(
            content_kind="affair",
            content_ref="demo_affair_b",
            content_payload={"template": "default"},
        ),
    )

    workflow.add_node(source_node)
    workflow.add_node(target_node)

    workflow.add_edge(
        Edge(
            uid="edge-1",
            source_node_uid="node-source",
            source_port_name="result",
            target_node_uid="node-target",
            target_port_name="in",
        )
    )

    return workflow


def main() -> None:
    """运行示例并打印工作流字典。"""

    workflow = build_minimal_workflow()
    print(workflow.to_dict())


if __name__ == "__main__":
    main()
