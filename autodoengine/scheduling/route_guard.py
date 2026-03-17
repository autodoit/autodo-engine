"""结果码守卫器。"""

from __future__ import annotations

from dataclasses import dataclass, field

from autodoengine.scheduling.types import AuditResult, GuardDecision, ResultCode, SelectionResult


@dataclass(slots=True)
class GuardPolicy:
    """守卫策略配置。"""

    max_retry: int = 2
    retryable_result_codes: set[str] = field(default_factory=lambda: {"RETRY"})
    blocking_audit_results: set[str] = field(default_factory=lambda: {"FAIL", "BLOCKED"})


@dataclass(slots=True)
class RouteGuard:
    """路由守卫器。"""

    policy: GuardPolicy = field(default_factory=GuardPolicy)

    def apply(
        self,
        result_code: ResultCode,
        audit_result: AuditResult,
        selection: SelectionResult,
        retry_count: int = 0,
    ) -> GuardDecision:
        """根据结果码和审计结果生成守卫决策。"""

        selected_transaction_uid: str | None = None
        if selection.selected is not None:
            selected_transaction_uid = selection.selected.edge.to_transaction_uid

        if audit_result in self.policy.blocking_audit_results:
            return GuardDecision(
                action="block",
                result_code=result_code,
                audit_result=audit_result,
                reason="审计未通过，强制阻断后续链路",
            )

        if result_code == "PASS":
            return GuardDecision(
                action="continue",
                result_code=result_code,
                audit_result=audit_result,
                reason="执行和审计均通过，可继续流转",
            )

        if result_code in self.policy.retryable_result_codes and retry_count < self.policy.max_retry:
            return GuardDecision(
                action="retry",
                result_code=result_code,
                audit_result=audit_result,
                reason="命中可重试结果码，进入重试分支",
                retry_transaction_uid=selected_transaction_uid,
            )

        if result_code in {"RETRY", "BACKTRACK"}:
            backtrack_transaction_uid: str | None = None
            if selection.ranked_candidates:
                backtrack_transaction_uid = selection.ranked_candidates[0].edge.from_transaction_uid
            return GuardDecision(
                action="backtrack",
                result_code=result_code,
                audit_result=audit_result,
                reason="重试超限或显式回退，返回最近稳定事务",
                backtrack_transaction_uid=backtrack_transaction_uid,
            )

        return GuardDecision(
            action="block",
            result_code=result_code,
            audit_result=audit_result,
            reason="执行结果无法自动处理，进入阻断状态",
        )

