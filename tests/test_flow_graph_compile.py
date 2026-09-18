"""V2 前端编译链行为测试（P2-1 救活后的功能验证）。

不止验证"能导入"，而是验证 AOF→FlowGraph→compiler 整链产出正确：
拓扑分层、workflow 结构、图字典往返、环检测、内容契约校验。
"""

from __future__ import annotations

import unittest

from autodoengine.flow_graph import (
    Edge,
    FlowGraph,
    FlowGraphError,
    Node,
    NodeContent,
    NodePort,
    compile_flow_graph_to_workflow_dict,
)
from autodoengine.flow_graph.compiler import _topological_layers


def _affair_node(uid: str, *, ref: str, in_port: str | None, out_port: str | None) -> Node:
    return Node(
        uid=uid,
        node_type="process",
        is_leaf=out_port is None,
        content=NodeContent(content_kind="affair", content_ref=ref, content_payload={}),
        input_ports={} if in_port is None else {in_port: NodePort(name=in_port)},
        output_ports={} if out_port is None else {out_port: NodePort(name=out_port)},
    )


class TestFlowGraphCompile(unittest.TestCase):
    def _linear_graph(self) -> FlowGraph:
        g = FlowGraph(uid="g-linear")
        g.add_node(_affair_node("a", ref="affair_a", in_port=None, out_port="x"))
        g.add_node(_affair_node("b", ref="affair_b", in_port="x", out_port="x"))
        g.add_node(_affair_node("c", ref="affair_c", in_port="x", out_port=None))
        g.add_edge(Edge(uid="e1", source_node_uid="a", source_port_name="x", target_node_uid="b", target_port_name="x"))
        g.add_edge(Edge(uid="e2", source_node_uid="b", source_port_name="x", target_node_uid="c", target_port_name="x"))
        return g

    def test_compile_linear_flow_topological_order(self) -> None:
        """三节点线性图应编译为按拓扑顺序排列的 flow 与逐层 flow_groups。"""

        g = self._linear_graph()
        from autodoengine.flow_graph import NodeTemplate

        # compiler 需要模板对象提供 affair 基配置；用最小替身。
        tmpl_map = {
            ref: NodeTemplate(
                id=ref,
                uid=f"tpl-{ref}",
                content_kind="affair",
                content_ref=ref,
                content_payload={},
                node_type="process",
                is_leaf=False,
                is_business_node=True,
                is_graph_node=False,
                allow_multi_input_ports=[],
                input_ports={"x": NodePort(name="x")},
                output_ports={"x": NodePort(name="x")},
                affair={"type": ref, "config": {}},
            )
            for ref in ("affair_a", "affair_b", "affair_c")
        }
        wf = compile_flow_graph_to_workflow_dict(g, templates_by_content_ref=tmpl_map)
        self.assertEqual(wf["schema_version"], "node_runtime_v2")
        self.assertEqual(wf["flow"], ["a", "b", "c"])
        self.assertEqual(wf["flow_groups"], [["a"], ["b"], ["c"]])
        self.assertEqual(set(wf["affairs"].keys()), {"a", "b", "c"})

    def test_cycle_detection_raises(self) -> None:
        """含环的图编译应抛 FlowGraphError。"""

        g = FlowGraph(uid="g-cycle")
        g.add_node(_affair_node("a", ref="affair_a", in_port="x", out_port="x"))
        g.add_node(_affair_node("b", ref="affair_b", in_port="x", out_port="x"))
        g.add_edge(Edge(uid="e1", source_node_uid="a", source_port_name="x", target_node_uid="b", target_port_name="x"))
        g.add_edge(Edge(uid="e2", source_node_uid="b", source_port_name="x", target_node_uid="a", target_port_name="x"))
        with self.assertRaises(FlowGraphError):
            _topological_layers(g)

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """图字典往返应保持节点与连线数量。"""

        g = self._linear_graph()
        g2 = FlowGraph.from_dict(g.to_dict())
        self.assertEqual(set(g2.nodes.keys()), {"a", "b", "c"})
        self.assertEqual(len(g2.edges), 2)

    def test_node_content_validation(self) -> None:
        """非法 content_kind / 空 content_ref 应报错。"""

        with self.assertRaises(FlowGraphError):
            NodeContent.from_mapping({"content_kind": "magic", "content_ref": "x"})
        with self.assertRaises(FlowGraphError):
            NodeContent.from_mapping({"content_kind": "affair", "content_ref": ""})
        ok = NodeContent.from_mapping({"content_kind": "affair", "content_ref": "x", "content_payload": {"a": 1}})
        self.assertEqual(ok.to_v2().content_payload, {"a": 1})


if __name__ == "__main__":
    unittest.main()
