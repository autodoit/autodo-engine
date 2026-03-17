"""任务数据库 Schema 注册表。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class ColumnSchema:
    """列定义。"""

    name: str
    required: bool = False
    default: str = ""
    description: str = ""


@dataclass(slots=True, frozen=True)
class TableSchema:
    """表定义。"""

    name: str
    primary_key: str
    columns: tuple[ColumnSchema, ...]
    description: str = ""

    @property
    def headers(self) -> list[str]:
        """导出表头列表。"""

        return [column.name for column in self.columns]


@dataclass(slots=True)
class SchemaRegistry:
    """Schema 注册表。"""

    version: str = "0.1.0"
    tables: dict[str, TableSchema] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "SchemaRegistry":
        """构建默认注册表。"""

        registry = cls()
        registry.tables = {
            "tasks": TableSchema(
                name="tasks",
                primary_key="task_uid",
                description="任务主表",
                columns=(
                    ColumnSchema("task_uid", required=True, description="任务 UID"),
                    ColumnSchema("name", required=True, description="任务名称"),
                    ColumnSchema("status", required=True, default="pending", description="任务状态"),
                    ColumnSchema("parent_task_uid", description="父任务 UID"),
                    ColumnSchema("priority", default="medium", description="优先级"),
                    ColumnSchema("current_transaction_uid", description="当前事务 UID"),
                    ColumnSchema("owner_agent", default="project-manager", description="拥有者 agent"),
                    ColumnSchema("created_at", required=True, description="创建时间"),
                    ColumnSchema("updated_at", required=True, description="更新时间"),
                ),
            ),
            "transactions": TableSchema(
                name="transactions",
                primary_key="transaction_uid",
                description="事务定义表",
                columns=(
                    ColumnSchema("transaction_uid", required=True, description="事务 UID"),
                    ColumnSchema("name", required=True, description="事务名称"),
                    ColumnSchema("level", required=True, default="L1", description="事务层级"),
                    ColumnSchema("input_schema_ref", description="输入 schema 引用"),
                    ColumnSchema("output_schema_ref", description="输出 schema 引用"),
                    ColumnSchema("retry_policy", default="default", description="重试策略"),
                    ColumnSchema("audit_policy", default="default", description="审计策略"),
                    ColumnSchema("version", default="0.1.0", description="版本号"),
                    ColumnSchema("enabled", default="true", description="是否启用"),
                ),
            ),
            "task_transaction_map": TableSchema(
                name="task_transaction_map",
                primary_key="map_uid",
                description="任务与事务映射表",
                columns=(
                    ColumnSchema("map_uid", required=True, description="映射 UID"),
                    ColumnSchema("task_uid", required=True, description="任务 UID"),
                    ColumnSchema("step_order", required=True, description="顺序"),
                    ColumnSchema("transaction_uid", required=True, description="事务 UID"),
                    ColumnSchema("step_status", required=True, default="pending", description="步骤状态"),
                    ColumnSchema("last_result_code", default="", description="最后结果码"),
                    ColumnSchema("started_at", description="开始时间"),
                    ColumnSchema("ended_at", description="结束时间"),
                ),
            ),
            "task_edges": TableSchema(
                name="task_edges",
                primary_key="edge_uid",
                description="任务路由边表",
                columns=(
                    ColumnSchema("edge_uid", required=True, description="边 UID"),
                    ColumnSchema("from_transaction_uid", description="起点事务 UID"),
                    ColumnSchema("to_transaction_uid", required=True, description="终点事务 UID"),
                    ColumnSchema("condition", default="always", description="边条件"),
                    ColumnSchema("active", default="true", description="是否启用"),
                    ColumnSchema("base_tendency_score", default="0", description="基础倾向得分"),
                    ColumnSchema("dynamic_delta", default="0", description="动态修正"),
                    ColumnSchema("transition_prob", default="1", description="转移概率"),
                    ColumnSchema("version", default="0.1.0", description="版本号"),
                ),
            ),
        }
        return registry

    def get(self, table_name: str) -> TableSchema:
        """获取表定义。"""

        return self.tables[table_name]
