"""图节点事务通用辅助模块。

本模块为图节点事务（start/end/if/fork/container/input/output/calc/compare）
提供统一的配置读取、表达式求值与结果落盘能力。

设计目标：
- 保持 P1 阶段“可运行占位实现”；
- 让图节点事务具备最小可观测性（可选输出报告文件）；
- 避免在多个事务文件中重复实现同样的样板代码。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from autodoengine.utils.expression_engine import evaluate_expression
from autodoengine.utils.path_tools import load_json_or_py


_ALLOWED_COMPARE_OPERATORS: Dict[str, Any] = {
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
}


def load_affair_config(config_path: Path | str) -> Dict[str, Any]:
    """读取图节点事务配置。

    Args:
        config_path: 调度器传入的配置文件路径。

    Returns:
        字典形式配置。若读取结果不是字典，返回空字典。
    """

    data = load_json_or_py(Path(config_path))
    if not isinstance(data, dict):
        return {}
    return data


def write_graph_node_report(
    *,
    config: Dict[str, Any],
    node_affair_name: str,
    report: Dict[str, Any],
) -> List[Path]:
    """按约定写出图节点运行报告。

    Args:
        config: 事务配置。
        node_affair_name: 图节点事务名。
        report: 需写出的报告内容。

    Returns:
        写出的文件路径列表。若未配置 output_dir，则返回空列表。
    """

    output_dir_raw = str(config.get("output_dir") or "").strip()
    if not output_dir_raw:
        return []

    output_dir = Path(output_dir_raw)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{node_affair_name}_report.json"
    report_path = output_dir / file_name

    payload = {
        "node_affair_name": node_affair_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "report": report,
    }
    report_path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return [report_path]


def compute_compare_result(*, left: Any, operator: str, right: Any) -> bool:
    """执行比较运算。

    Args:
        left: 左操作数。
        operator: 比较运算符，支持 `==`、`!=`、`>`、`>=`、`<`、`<=`。
        right: 右操作数。

    Returns:
        比较结果布尔值。

    Raises:
        ValueError: 运算符不受支持。
    """

    op = str(operator).strip()
    fn = _ALLOWED_COMPARE_OPERATORS.get(op)
    if fn is None:
        raise ValueError(f"不支持的比较运算符：{operator}")
    return bool(fn(left, right))


def compute_simple_expression(
    *,
    expression: str,
    variables: Dict[str, Any] | None = None,
    mode: str = "safe",
    allow_unsafe_eval: bool = False,
) -> Dict[str, Any]:
    """计算受限表达式。

    注意：
    - 仅在受限的全局上下文下执行表达式；
    - 用于 P1 占位计算节点，不用于执行任意脚本。

    Args:
        expression: 表达式字符串。
        variables: 可用变量字典。
        mode: 表达式引擎模式，支持 `safe`、`auto`、`eval`。
        allow_unsafe_eval: 是否允许回退到 `eval`。

    Returns:
        字典，包含 `value`、`engine`、`warning`。

    Raises:
        ValueError: 表达式为空。
    """

    expr = str(expression or "").strip()
    if not expr:
        raise ValueError("expression 不能为空")

    result = evaluate_expression(
        expression=expr,
        variables=dict(variables or {}),
        mode=mode,
        allow_unsafe_eval=allow_unsafe_eval,
    )
    return {
        "value": result.value,
        "engine": result.engine,
        "warning": result.warning,
    }

