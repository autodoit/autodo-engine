"""表达式求值引擎。

本模块提供统一的表达式求值能力，默认使用专用解释器（simpleeval），
并支持在显式开启时回退到 `eval`（高风险，默认关闭）。

安全设计：
- 默认模式为 `safe`，仅允许白名单函数与变量；
- `eval` 仅在 `allow_unsafe_eval=True` 时可用，并返回风险告警；
- 所有调用方应记录 `engine` 与 `warning`，用于审计追踪。
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any, Callable, Dict, Mapping


class ExpressionEngineError(ValueError):
    """表达式引擎异常。"""


@dataclass(slots=True, frozen=True)
class ExpressionEvalResult:
    """表达式求值结果。

    Args:
        value: 求值结果。
        engine: 实际使用的引擎标识（`simpleeval` 或 `eval`）。
        warning: 可选风险提示。
    """

    value: Any
    engine: str
    warning: str | None = None


def _default_allowed_functions() -> Dict[str, Callable[..., Any]]:
    """返回默认允许的函数白名单。

    Returns:
        函数映射字典。

    Examples:
        >>> funcs = _default_allowed_functions()
        >>> "min" in funcs
        True
    """

    return {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "len": len,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
    }


def evaluate_expression(
    *,
    expression: str,
    variables: Mapping[str, Any] | None = None,
    mode: str = "safe",
    allow_unsafe_eval: bool = False,
    allowed_functions: Mapping[str, Callable[..., Any]] | None = None,
) -> ExpressionEvalResult:
    """求值表达式。

    Args:
        expression: 表达式字符串。
        variables: 变量映射。
        mode: 求值模式，支持 `safe`、`eval`、`auto`。
        allow_unsafe_eval: 是否允许回退到 `eval`。
        allowed_functions: 可用函数白名单。

    Returns:
        ExpressionEvalResult: 求值结果与引擎信息。

    Raises:
        ExpressionEngineError: 表达式为空、模式非法或求值失败。

    Examples:
        >>> result = evaluate_expression(expression="x + 1", variables={"x": 1})
        >>> result.value
        2
    """

    expr = str(expression or "").strip()
    if not expr:
        raise ExpressionEngineError("expression 不能为空")

    normalized_mode = str(mode or "safe").strip().lower()
    if normalized_mode not in {"safe", "eval", "auto"}:
        raise ExpressionEngineError(f"不支持的表达式模式：{mode}")

    names = dict(variables or {})
    functions = dict(_default_allowed_functions())
    if allowed_functions:
        functions.update(dict(allowed_functions))

    prefer_safe = normalized_mode in {"safe", "auto"}
    if prefer_safe:
        try:
            simpleeval_mod = importlib.import_module("simpleeval")
            SimpleEval = getattr(simpleeval_mod, "SimpleEval")

            evaluator = SimpleEval()
            evaluator.names = names
            evaluator.functions = functions
            value = evaluator.eval(expr)
            return ExpressionEvalResult(value=value, engine="simpleeval", warning=None)
        except ModuleNotFoundError as exc:
            if normalized_mode == "safe" and not allow_unsafe_eval:
                raise ExpressionEngineError(
                    "安全表达式引擎不可用：缺少 simpleeval 依赖。"
                    "请安装依赖或显式开启 allow_unsafe_eval。"
                ) from exc
        except Exception as exc:  # noqa: BLE001
            if normalized_mode == "safe":
                raise ExpressionEngineError(f"safe 模式表达式求值失败：{exc}") from exc

    if normalized_mode == "eval" or allow_unsafe_eval:
        safe_globals = {"__builtins__": functions}
        try:
            value = eval(expr, safe_globals, names)
        except Exception as exc:  # noqa: BLE001
            raise ExpressionEngineError(f"eval 模式表达式求值失败：{exc}") from exc
        return ExpressionEvalResult(
            value=value,
            engine="eval",
            warning="当前表达式通过 eval 执行，存在安全风险。建议切换为 safe 模式。",
        )

    raise ExpressionEngineError("表达式求值失败：safe 模式不可用，且未允许 eval 回退。")


def evaluate_predicate(
    *,
    expression: str,
    variables: Mapping[str, Any] | None = None,
    mode: str = "safe",
    allow_unsafe_eval: bool = False,
    allowed_functions: Mapping[str, Callable[..., Any]] | None = None,
) -> ExpressionEvalResult:
    """求值布尔表达式。

    Args:
        expression: 表达式字符串。
        variables: 变量映射。
        mode: 求值模式。
        allow_unsafe_eval: 是否允许 eval 回退。
        allowed_functions: 可用函数白名单。

    Returns:
        ExpressionEvalResult: 布尔结果与引擎信息。

    Raises:
        ExpressionEngineError: 表达式求值失败。

    Examples:
        >>> result = evaluate_predicate(expression="x > 0", variables={"x": 1})
        >>> result.value
        True
    """

    result = evaluate_expression(
        expression=expression,
        variables=variables,
        mode=mode,
        allow_unsafe_eval=allow_unsafe_eval,
        allowed_functions=allowed_functions,
    )
    return ExpressionEvalResult(value=bool(result.value), engine=result.engine, warning=result.warning)
