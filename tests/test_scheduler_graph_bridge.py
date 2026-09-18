"""调度脊柱 ↔ 图模型 适配层测试（P2-4 对照）。

证明 SchedulerService 能在真实 `Graph` 上完成下一跳选择：
- 线性图：与轨道 A 的"过滤后取首边"结果一致；
- 分支图：按 `base_tendency_score` 选高分边（相对 A 的任意取首，是有意的评分升级）。
"""

from __future__ import annotations

import unittest

from autodoengine.flow_graph.models import Graph, GraphEdge, GraphNode
from autodoengine.flow_graph.route_view import (
    build_candidate_edges,
    filter_edges_by_condition,
    filter_enabled_edges,
)
from autodoengine.scheduling.candidate_builder import CandidateBuilder
from autodoengine.scheduling.dispatch_executor import DispatchExecutor
from autodoengine.scheduling.edge_scorer import EdgeScorer
from autodoengine.scheduling.graph_bridge import select_next_edge
from autodoengine.scheduling.route_guard import RouteGuard
from autodoengine.scheduling.route_selector import RouteSelector
from autodoengine.scheduling.service import SchedulerService
from autodoengine.scheduling.types import SchedulerContext


def _node(uid: str) -> GraphNode:
    return GraphNode(node_uid=uid, node_type="process", affair_uid=None, container_id=None)


def _service() -> SchedulerService:
    return SchedulerService(
        candidate_builder=CandidateBuilder(),
        edge_scorer=EdgeScorer(),
        route_selector=RouteSelector(),
        route_guard=RouteGuard(),
        dispatch_executor=DispatchExecutor(),
    )


def _live_candidates(graph: Graph, current_uid: str):
    """复刻轨道 A 的候选过滤（enabled + condition）。"""

    edges = filter_enabled_edges(build_candidate_edges(graph, current_uid))
    node = graph.nodes[current_uid]
    return filter_edges_by_condition(
        edges,
        task_context={"task_uid": "t", "status": "running", "retry_count": 0, "goal_text": "g", "metadata": {}},
        node_context=type("NC", (), {"node_uid": node.node_uid, "node_type": node.node_type, "risk_level": node.risk_level, "policies": node.policies})(),
    )


class TestSchedulerGraphBridge(unittest.TestCase):
    def test_linear_agrees_with_track_a(self) -> None:
        g = Graph(graph_uid="g", graph_name="g", graph_version="1",
                  nodes={u: _node(u) for u in ("a", "b")},
                  edges=[GraphEdge(edge_uid="e_ab", from_node_uid="a", to_node_uid="b", base_tendency_score=1.0)])
        ctx = SchedulerContext(task_uid="t", goal="g", current_transaction_uid="a")
        picked = select_next_edge(_service(), graph=g, context=ctx, candidate_edges=_live_candidates(g, "a"))
        self.assertIsNotNone(picked)
        self.assertEqual(picked.edge_uid, "e_ab")
        self.assertEqual(g.nodes[picked.to_node_uid].node_uid, "b")

    def test_branch_picks_high_scorer(self) -> None:
        g = Graph(graph_uid="g", graph_name="g", graph_version="1",
                  nodes={u: _node(u) for u in ("a", "b", "c")},
                  edges=[
                      GraphEdge(edge_uid="e_ab", from_node_uid="a", to_node_uid="b", base_tendency_score=1.0),
                      GraphEdge(edge_uid="e_ac", from_node_uid="a", to_node_uid="c", base_tendency_score=5.0),
                  ])
        ctx = SchedulerContext(task_uid="t", goal="g", current_transaction_uid="a")
        picked = select_next_edge(_service(), graph=g, context=ctx, candidate_edges=_live_candidates(g, "a"))
        self.assertEqual(picked.edge_uid, "e_ac")  # 高分边优先

    def test_disabled_edge_not_selected(self) -> None:
        g = Graph(graph_uid="g", graph_name="g", graph_version="1",
                  nodes={u: _node(u) for u in ("a", "b")},
                  edges=[GraphEdge(edge_uid="e_ab", from_node_uid="a", to_node_uid="b", base_tendency_score=1.0, enabled=False)])
        ctx = SchedulerContext(task_uid="t", goal="g", current_transaction_uid="a")
        picked = select_next_edge(_service(), graph=g, context=ctx, candidate_edges=_live_candidates(g, "a"))
        self.assertIsNone(picked)


if __name__ == "__main__":
    unittest.main()
