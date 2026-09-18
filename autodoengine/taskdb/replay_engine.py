"""任务回放引擎。

从执行日志（JSONL）重建每个任务最近一次事务的步骤状态，作为轨迹分析/审计复现的地基。

历史死因 C：曾依赖 `state_machine.TransactionStateMachine` 类，该类已在
"类→函数"重构中移除；本模块改为直接使用 `core.enums.ResultCode` 的中英映射，
不再依赖已废弃的状态机类。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autodoengine.core.enums import ResultCode


def status_from_result_code(result_code: str) -> str:
    """把事务结果码映射为回放用的中文步骤状态。

    Args:
        result_code: 结果码，接受英文值（PASS/RETRY/BACKTRACK/BLOCKED）或中文持久化值。

    Returns:
        对应的中文步骤状态（通过/重试/回退/阻断）；无法识别时按"阻断"处理。
    """

    try:
        return ResultCode.normalize(result_code).db_value
    except ValueError:
        return ResultCode.BLOCKED.db_value


@dataclass(slots=True)
class ReplayEngine:
    """回放引擎。"""

    execution_log_path: Path

    def replay(self) -> dict[str, dict[str, Any]]:
        """按 task_uid 汇总最近一次事务的状态快照。

        Returns:
            以 task_uid 为键、最近状态为值的字典；日志不存在时返回空字典。
        """

        latest_task_states: dict[str, dict[str, Any]] = {}
        if not self.execution_log_path.exists():
            return latest_task_states

        with self.execution_log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                result_code: str = str(item.get("result_code", "BLOCKED"))
                latest_task_states[item["task_uid"]] = {
                    "last_transaction_uid": item.get("transaction_uid", ""),
                    "last_result_code": result_code,
                    "step_status": status_from_result_code(result_code),
                    "audit_result": item.get("audit_result", ""),
                    "ended_at": item.get("ended_at", ""),
                }
        return latest_task_states
