"""候选事务构建器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from autodoengine.scheduling.types import CandidateEdge, CandidateSet, SchedulerContext


@dataclass(slots=True)
class CandidateBuilder:
    """候选构建器。"""

    allow_revisit: bool = True

    def build_candidates(
        self,
        context: SchedulerContext,
        edges: Iterable[CandidateEdge],
    ) -> CandidateSet:
        """构建候选集合。"""

        candidates: list[CandidateEdge] = []
        blocked_reasons: dict[str, str] = {}

        for edge in edges:
            reason = self._block_reason(edge=edge, context=context)
            if reason is not None:
                blocked_reasons[edge.edge_uid] = reason
                continue
            candidates.append(edge)

        return CandidateSet(
            task_uid=context.task_uid,
            current_transaction_uid=context.current_transaction_uid,
            candidates=tuple(candidates),
            blocked_reasons=blocked_reasons,
        )

    def _block_reason(
        self,
        edge: CandidateEdge,
        context: SchedulerContext,
    ) -> str | None:
        """判断单条边的阻断原因。"""

        if not edge.active:
            return "边已停用"
        if edge.blocked_by_audit:
            return "被审计硬约束阻断"
        if edge.from_transaction_uid not in {None, context.current_transaction_uid}:
            return "起点事务与当前上下文不匹配"
        if not self.allow_revisit and edge.to_transaction_uid in context.completed_transactions:
            return "目标事务已完成且不允许重访"
        if edge.to_transaction_uid in context.failed_transactions:
            return "目标事务已被标记为失败事务"
        if not self._has_required_permissions(edge=edge, context=context):
            return "缺少执行该事务所需权限"
        if not self._preconditions_satisfied(edge=edge, context=context):
            return "前置条件未满足"
        return None

    def _has_required_permissions(
        self,
        edge: CandidateEdge,
        context: SchedulerContext,
    ) -> bool:
        """校验权限集合。"""

        return set(edge.required_permissions).issubset(context.permission_flags)

    def _preconditions_satisfied(
        self,
        edge: CandidateEdge,
        context: SchedulerContext,
    ) -> bool:
        """校验简单前置条件。"""

        condition: str = edge.condition.strip()
        if not condition or condition == "always":
            return True
        if condition.startswith("needs_completed:"):
            required_transaction_uid: str = condition.split(":", 1)[1].strip()
            return required_transaction_uid in context.completed_transactions
        return True

