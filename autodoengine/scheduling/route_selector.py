"""路由选择器。"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from autodoengine.scheduling.types import ScoredCandidate, SelectionResult, SelectionStrategy


@dataclass(slots=True)
class RouteSelector:
    """路由选择器。"""

    seed: int = 20260306

    def select_next(
        self,
        scored_candidates: tuple[ScoredCandidate, ...],
        strategy: SelectionStrategy = "argmax",
        temperature: float = 1.0,
    ) -> SelectionResult:
        """选择下一事务。"""

        if not scored_candidates:
            return SelectionResult(
                selected=None,
                ranked_candidates=(),
                strategy=strategy,
                reason="无可用候选事务",
                alternatives=(),
            )

        if strategy == "softmax":
            selected_candidate: ScoredCandidate = self._softmax_pick(
                scored_candidates=scored_candidates,
                temperature=temperature,
            )
            reason: str = f"使用 softmax 策略完成采样，temperature={temperature}"
        else:
            selected_candidate = scored_candidates[0]
            reason = "使用 argmax 策略选择最高得分候选"

        alternatives: tuple[str, ...] = tuple(
            item.edge.to_transaction_uid for item in scored_candidates[1:]
        )
        return SelectionResult(
            selected=selected_candidate,
            ranked_candidates=scored_candidates,
            strategy=strategy,
            reason=reason,
            alternatives=alternatives,
        )

    def _softmax_pick(
        self,
        scored_candidates: tuple[ScoredCandidate, ...],
        temperature: float,
    ) -> ScoredCandidate:
        """执行 softmax 采样。"""

        safe_temperature: float = max(temperature, 1e-6)
        max_score: float = max(item.score for item in scored_candidates)
        exp_values: list[float] = [
            math.exp((item.score - max_score) / safe_temperature)
            for item in scored_candidates
        ]
        total: float = sum(exp_values)
        probabilities: list[float] = [value / total for value in exp_values]

        rng: random.Random = random.Random(self.seed)
        threshold: float = rng.random()
        cumulative: float = 0.0
        for candidate, probability in zip(scored_candidates, probabilities, strict=True):
            cumulative += probability
            if threshold <= cumulative:
                return candidate
        return scored_candidates[-1]

