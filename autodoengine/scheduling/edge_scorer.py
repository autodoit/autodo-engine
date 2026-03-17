"""候选边评分器。"""

from __future__ import annotations

from dataclasses import dataclass

from autodoengine.scheduling.types import CandidateSet, SchedulerContext, ScoredCandidate


@dataclass(slots=True)
class ScoreWeights:
    """评分权重。"""

    base: float = 1.0
    goal_gain: float = 1.0
    risk_penalty: float = 1.0
    cost_penalty: float = 1.0
    time_penalty: float = 1.0
    audit_bonus: float = 1.0
    dynamic_delta: float = 1.0


@dataclass(slots=True)
class EdgeScorer:
    """边评分器。"""

    def score_edges(
        self,
        candidates: CandidateSet,
        context: SchedulerContext,
        weights: ScoreWeights | None = None,
    ) -> tuple[ScoredCandidate, ...]:
        """为候选边打分。"""

        active_weights: ScoreWeights = weights or ScoreWeights()
        scored_candidates: list[ScoredCandidate] = []

        for edge in candidates.candidates:
            runtime_goal_gain: float = context.runtime_features.get("goal_gain", edge.goal_gain)
            runtime_risk_penalty: float = context.runtime_features.get("risk_penalty", edge.risk_penalty)
            runtime_cost_penalty: float = context.runtime_features.get("cost_penalty", edge.cost_penalty)
            runtime_time_penalty: float = context.runtime_features.get("time_penalty", edge.time_penalty)
            runtime_audit_bonus: float = context.runtime_features.get("audit_bonus", edge.audit_bonus)

            score: float = (
                active_weights.base * edge.base_tendency_score
                + active_weights.goal_gain * runtime_goal_gain
                - active_weights.risk_penalty * runtime_risk_penalty
                - active_weights.cost_penalty * runtime_cost_penalty
                - active_weights.time_penalty * runtime_time_penalty
                + active_weights.audit_bonus * runtime_audit_bonus
                + active_weights.dynamic_delta * edge.dynamic_delta
            )

            scored_candidates.append(
                ScoredCandidate(
                    edge=edge,
                    score=score,
                    explain={
                        "base_tendency_score": edge.base_tendency_score,
                        "goal_gain": runtime_goal_gain,
                        "risk_penalty": runtime_risk_penalty,
                        "cost_penalty": runtime_cost_penalty,
                        "time_penalty": runtime_time_penalty,
                        "audit_bonus": runtime_audit_bonus,
                        "dynamic_delta": edge.dynamic_delta,
                    },
                )
            )

        scored_candidates.sort(key=lambda item: item.score, reverse=True)
        return tuple(scored_candidates)

