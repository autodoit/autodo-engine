"""调度服务编排入口。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from autodoengine.scheduling.candidate_builder import CandidateBuilder
from autodoengine.scheduling.dispatch_executor import DispatchExecutor
from autodoengine.scheduling.edge_scorer import EdgeScorer, ScoreWeights
from autodoengine.scheduling.event_logger import DispatchEventLogger
from autodoengine.scheduling.route_guard import RouteGuard
from autodoengine.scheduling.route_selector import RouteSelector
from autodoengine.scheduling.types import (
    AuditResult,
    CandidateEdge,
    DispatchEvent,
    ResultCode,
    SchedulerContext,
)


@dataclass(slots=True)
class SchedulerService:
    """调度服务。"""

    candidate_builder: CandidateBuilder
    edge_scorer: EdgeScorer
    route_selector: RouteSelector
    route_guard: RouteGuard
    dispatch_executor: DispatchExecutor
    event_logger: DispatchEventLogger | None = None

    def dispatch_once(
        self,
        context: SchedulerContext,
        edges: tuple[CandidateEdge, ...],
        payload: dict[str, object],
        weights: ScoreWeights | None = None,
        strategy: str = "argmax",
        execute: bool = False,
        result_code: ResultCode = "PASS",
        audit_result: AuditResult = "PASS",
    ) -> DispatchEvent:
        """执行单轮调度。"""

        candidate_set = self.candidate_builder.build_candidates(context=context, edges=edges)
        scored_candidates = self.edge_scorer.score_edges(
            candidates=candidate_set,
            context=context,
            weights=weights,
        )
        selection = self.route_selector.select_next(
            scored_candidates=scored_candidates,
            strategy=strategy,
        )
        receipt = self.dispatch_executor.dispatch(
            selection=selection,
            payload=payload,
            execute=execute,
        )
        retry_count: int = 0
        if selection.selected is not None:
            retry_count = context.retry_counts.get(selection.selected.edge.to_transaction_uid, 0)
        guard_decision = self.route_guard.apply(
            result_code=result_code,
            audit_result=audit_result,
            selection=selection,
            retry_count=retry_count,
        )

        event = DispatchEvent(
            event_uid=f"dispatch-{uuid4().hex}",
            task_uid=context.task_uid,
            selection=selection,
            guard_decision=guard_decision,
            receipt=receipt,
        )
        if self.event_logger is not None:
            self.event_logger.emit(event)
        return event

