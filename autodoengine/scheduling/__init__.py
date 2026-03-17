"""调度闭环模块。"""

from .candidate_builder import CandidateBuilder
from .dispatch_executor import DispatchExecutor
from .edge_scorer import EdgeScorer, ScoreWeights
from .event_logger import DispatchEventLogger
from .route_guard import GuardPolicy, RouteGuard
from .route_selector import RouteSelector
from .service import SchedulerService
from .types import (
    AuditResult,
    CandidateEdge,
    CandidateSet,
    DispatchEvent,
    DispatchKind,
    DispatchReceipt,
    GuardDecision,
    ResultCode,
    SchedulerContext,
    ScoredCandidate,
    SelectionResult,
    SelectionStrategy,
)
from .result_protocol import (
    build_backtrack_receipt,
    build_blocked_receipt,
    build_pass_receipt,
    build_retry_receipt,
    normalize_receipt,
    validate_receipt,
)
from .candidate_actions import (
    build_candidate_actions,
    build_decision_packet,
    collect_rule_hits,
    rank_candidate_actions,
)
from .pa_decision_adapter import normalize_decision_result, request_pa_decision, validate_decision_result
from .task_dispatcher import (
    prepare_history_summary,
    prepare_node_context,
    prepare_retry_budget,
    prepare_task_context,
)
from .task_loop import (
    apply_decision_result,
    run_task_step,
    run_task_until_terminal,
    run_task_until_wait,
    write_task_step_records,
)
from .block_scope_lifter import BlockScopeLiftResult, lift_block_scope

__all__ = [
    "AuditResult",
    "CandidateBuilder",
    "CandidateEdge",
    "CandidateSet",
    "DispatchEvent",
    "DispatchEventLogger",
    "DispatchExecutor",
    "DispatchKind",
    "DispatchReceipt",
    "EdgeScorer",
    "GuardDecision",
    "GuardPolicy",
    "ResultCode",
    "RouteGuard",
    "RouteSelector",
    "SchedulerContext",
    "SchedulerService",
    "ScoreWeights",
    "ScoredCandidate",
    "SelectionResult",
    "SelectionStrategy",
    "normalize_receipt",
    "validate_receipt",
    "build_pass_receipt",
    "build_retry_receipt",
    "build_backtrack_receipt",
    "build_blocked_receipt",
    "collect_rule_hits",
    "rank_candidate_actions",
    "build_decision_packet",
    "build_candidate_actions",
    "request_pa_decision",
    "normalize_decision_result",
    "validate_decision_result",
    "prepare_task_context",
    "prepare_node_context",
    "prepare_retry_budget",
    "prepare_history_summary",
    "apply_decision_result",
    "write_task_step_records",
    "BlockScopeLiftResult",
    "lift_block_scope",
    "run_task_step",
    "run_task_until_wait",
    "run_task_until_terminal",
]
