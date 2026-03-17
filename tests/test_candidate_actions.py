"""candidate_actions 单元测试。"""

from __future__ import annotations

import unittest

from autodoengine.core.enums import BlockReasonCode, BlockScope, ResultCode, TaskAction, TaskStatus
from autodoengine.core.types import NodeContext, ResultReceipt, RetryBudget, TaskContext
from autodoengine.scheduling.candidate_actions import build_candidate_actions, rank_candidate_actions


class TestCandidateActions(unittest.TestCase):
    """候选动作生成测试。"""

    def _build_task_context(self) -> TaskContext:
        return TaskContext(
            task_uid="task-1",
            graph_uid="graph-1",
            status=TaskStatus.RUNNING,
            current_node_uid="node-1",
            current_affair_uid="affair-1",
            goal_text="测试",
            retry_count=0,
            max_retry=2,
            metadata={},
        )

    def test_rank_candidate_actions(self) -> None:
        """动作排序应遵循固定优先级。"""

        ranked = rank_candidate_actions([TaskAction.FAIL, TaskAction.HUMAN_GATE, TaskAction.RETRY])
        self.assertEqual(ranked, [TaskAction.HUMAN_GATE, TaskAction.RETRY, TaskAction.FAIL])

    def test_blocked_human_gate_priority(self) -> None:
        """BLOCKED 且 requires_human 时应优先 human_gate。"""

        task_context = self._build_task_context()
        node_context = NodeContext(
            node_uid="node-1",
            node_type="process",
            affair_uid="affair-1",
            risk_level="normal",
            policies={},
        )
        receipt = ResultReceipt(
            result_code=ResultCode.BLOCKED,
            block_reason_code=BlockReasonCode.PERMISSION_MISSING,
            block_scope=BlockScope.AFFAIR,
            requires_human=True,
            retryable=False,
        )
        packet = build_candidate_actions(
            receipt=receipt,
            task_context=task_context,
            node_context=node_context,
            retry_budget=RetryBudget(max_retry=2, current_retry=0),
            history_summary={"split_hint": False},
        )

        self.assertGreaterEqual(len(packet.candidate_actions), 1)
        self.assertEqual(packet.recommended_action, TaskAction.HUMAN_GATE)

    def test_pass_complete(self) -> None:
        """PASS 且 goal_satisfied 时推荐 complete。"""

        task_context = self._build_task_context()
        task_context.metadata["goal_satisfied"] = True
        node_context = NodeContext(
            node_uid="node-1",
            node_type="process",
            affair_uid="affair-1",
            risk_level="normal",
            policies={},
        )
        receipt = ResultReceipt(result_code=ResultCode.PASS)
        packet = build_candidate_actions(
            receipt=receipt,
            task_context=task_context,
            node_context=node_context,
            retry_budget=RetryBudget(max_retry=2, current_retry=0),
            history_summary={"split_hint": False},
        )
        self.assertEqual(packet.recommended_action, TaskAction.COMPLETE)


if __name__ == "__main__":
    unittest.main()

