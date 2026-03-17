"""完整性校验模块。"""

from __future__ import annotations

from dataclasses import dataclass

from autodoengine.taskdb.schema_registry import SchemaRegistry
from autodoengine.taskdb.state_machine import TaskStateMachine, TransactionStateMachine


@dataclass(slots=True)
class IntegrityChecker:
    """完整性校验器。"""

    schema_registry: SchemaRegistry
    task_state_machine: TaskStateMachine
    transaction_state_machine: TransactionStateMachine

    def check_primary_keys(self, table_name: str, rows: list[dict[str, str]]) -> list[str]:
        """检查主键唯一性。"""

        schema = self.schema_registry.get(table_name)
        seen: set[str] = set()
        errors: list[str] = []
        for row in rows:
            primary_key = row.get(schema.primary_key, "")
            if not primary_key:
                errors.append(f"{table_name} 缺少主键字段 {schema.primary_key}")
                continue
            if primary_key in seen:
                errors.append(f"{table_name} 存在重复主键：{primary_key}")
            seen.add(primary_key)
        return errors

    def check_task_relationships(
        self,
        tasks_rows: list[dict[str, str]],
        map_rows: list[dict[str, str]],
        transaction_rows: list[dict[str, str]],
    ) -> list[str]:
        """检查任务与事务映射完整性。"""

        task_uids: set[str] = {row.get("task_uid", "") for row in tasks_rows}
        transaction_uids: set[str] = {row.get("transaction_uid", "") for row in transaction_rows}
        errors: list[str] = []
        for row in map_rows:
            if row.get("task_uid", "") not in task_uids:
                errors.append(f"映射表引用了不存在的 task_uid：{row.get('task_uid', '')}")
            if row.get("transaction_uid", "") not in transaction_uids:
                errors.append(f"映射表引用了不存在的 transaction_uid：{row.get('transaction_uid', '')}")
        return errors

    def check_step_status(self, step_rows: list[dict[str, str]]) -> list[str]:
        """检查步骤状态是否合法。"""

        allowed: set[str] = set(self.transaction_state_machine.transitions.keys())
        allowed.update({"completed", "retrying", "backtracked", "blocked"})
        errors: list[str] = []
        for row in step_rows:
            step_status = row.get("step_status", "")
            if step_status and step_status not in allowed:
                errors.append(f"非法步骤状态：{step_status}")
        return errors

    def check_edge_ranges(self, edge_rows: list[dict[str, str]]) -> list[str]:
        """检查边数值区间是否合法。"""

        errors: list[str] = []
        for row in edge_rows:
            try:
                score = float(row.get("base_tendency_score", "0") or 0)
                probability = float(row.get("transition_prob", "1") or 1)
            except ValueError:
                errors.append(f"边表数值字段不是合法数字：{row.get('edge_uid', '')}")
                continue
            if not 0 <= score <= 100:
                errors.append(f"base_tendency_score 超出范围：{row.get('edge_uid', '')}")
            if not 0 <= probability <= 1:
                errors.append(f"transition_prob 超出范围：{row.get('edge_uid', '')}")
        return errors

