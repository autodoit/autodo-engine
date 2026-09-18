"""SchedulerService（调度五件套）行为测试。

设计基准 F2 要求"SchedulerService 命中主链且有测试"（此前零覆盖）。
本测试先固化 Filter→Score→Select→Guard→Dispatch 的既有行为，
作为 P2-4 双轨合一前"新脊柱正确性"的护栏。
"""

from __future__ import annotations

import unittest

from autodoengine.scheduling.candidate_builder import CandidateBuilder
from autodoengine.scheduling.dispatch_executor import DispatchExecutor
from autodoengine.scheduling.edge_scorer import EdgeScorer
from autodoengine.scheduling.route_guard import RouteGuard
from autodoengine.scheduling.route_selector import RouteSelector
from autodoengine.scheduling.service import SchedulerService
from autodoengine.scheduling.types import CandidateEdge, SchedulerContext


def _service() -> SchedulerService:
    return SchedulerService(
        candidate_builder=CandidateBuilder(),
        edge_scorer=EdgeScorer(),
        route_selector=RouteSelector(),
        route_guard=RouteGuard(),
        dispatch_executor=DispatchExecutor(
            dispatch_map={
                "run_t1": {"kind": "python_callable", "target": "noop"},
                "run_t2": {"kind": "python_callable", "target": "noop"},
            }
        ),
    )


def _context() -> SchedulerContext:
    return SchedulerContext(task_uid="task-1", goal="demo", current_transaction_uid="t0")


class TestSchedulerService(unittest.TestCase):
    def test_dispatch_once_pass_continues_and_picks_high_scorer(self) -> None:
        """两条候选时应选高分边，PASS 结果守卫为 continue。"""

        edges = (
            CandidateEdge(edge_uid="e1", from_transaction_uid="t0", to_transaction_uid="t1", base_tendency_score=1.0, dispatch_key="run_t1"),
            CandidateEdge(edge_uid="e2", from_transaction_uid="t0", to_transaction_uid="t2", base_tendency_score=5.0, dispatch_key="run_t2"),
        )
        event = _service().dispatch_once(context=_context(), edges=edges, payload={}, result_code="PASS")

        self.assertIsNotNone(event.selection.selected)
        self.assertEqual(event.selection.selected.edge.to_transaction_uid, "t2")
        self.assertEqual(event.guard_decision.action, "continue")
        self.assertTrue(event.receipt.accepted)

    def test_dispatch_once_audit_fail_blocks(self) -> None:
        """审计 FAIL 应强制 block。"""

        edges = (
            CandidateEdge(edge_uid="e1", from_transaction_uid="t0", to_transaction_uid="t1", base_tendency_score=1.0, dispatch_key="run_t1"),
        )
        event = _service().dispatch_once(context=_context(), edges=edges, payload={}, result_code="PASS", audit_result="FAIL")
        self.assertEqual(event.guard_decision.action, "block")

    def test_dispatch_once_no_candidates(self) -> None:
        """无可用候选时选中为空、回执未接受。"""

        event = _service().dispatch_once(context=_context(), edges=(), payload={}, result_code="PASS")
        self.assertIsNone(event.selection.selected)
        self.assertFalse(event.receipt.accepted)

    def test_candidate_blocked_when_from_mismatch(self) -> None:
        """起点事务与当前上下文不匹配的边应被 Filter 掉。"""

        edges = (
            CandidateEdge(edge_uid="e1", from_transaction_uid="other", to_transaction_uid="t1", dispatch_key="run_t1"),
        )
        event = _service().dispatch_once(context=_context(), edges=edges, payload={}, result_code="PASS")
        self.assertIsNone(event.selection.selected)

    def test_retry_then_backtrack_on_retry_exhaust(self) -> None:
        """RETRY 未超限→retry；超限→backtrack。"""

        edges = (
            CandidateEdge(edge_uid="e1", from_transaction_uid="t0", to_transaction_uid="t1", dispatch_key="run_t1"),
        )
        ctx = _context()
        svc = _service()
        # retry_counts[t1]=0 < max_retry(2) → retry
        e_retry = svc.dispatch_once(context=ctx, edges=edges, payload={}, result_code="RETRY")
        self.assertEqual(e_retry.guard_decision.action, "retry")
        # 超限
        ctx_hot = SchedulerContext(task_uid="task-1", goal="demo", current_transaction_uid="t0", retry_counts={"t1": 5})
        e_back = svc.dispatch_once(context=ctx_hot, edges=edges, payload={}, result_code="RETRY")
        self.assertEqual(e_back.guard_decision.action, "backtrack")


if __name__ == "__main__":
    unittest.main()
