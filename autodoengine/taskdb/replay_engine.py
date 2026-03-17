"""任务回放引擎。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autodoengine.taskdb.state_machine import TransactionStateMachine


@dataclass(slots=True)
class ReplayEngine:
    """回放引擎。"""

    execution_log_path: Path
    transaction_state_machine: TransactionStateMachine

    def replay(self) -> dict[str, Any]:
        """重建最近状态快照。"""

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
                    "step_status": self.transaction_state_machine.status_from_result_code(result_code),
                    "audit_result": item.get("audit_result", ""),
                    "ended_at": item.get("ended_at", ""),
                }
        return latest_task_states

