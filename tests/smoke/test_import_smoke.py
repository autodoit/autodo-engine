"""引擎冒烟测试（CI 必跑门）。

目标：把"引擎能不能被导入、关键存活契约在不在"变成秒级可判定的门，
避免像历史上那样"断裂潜伏半年无人发现"。

分两类：
- 硬断言（必须通过）：引擎主 API、AOK `run_affair`、已修复依赖的 `skill_renderer`。
- xfail（已知坏死、登记在案）：`flow_graph` 四模块与 `taskdb.replay_engine`，
  对应设计基准 §11.1 的死因 A / C，待 P2（救活 V2 流水线）与并行·C 类迁移修复。
  一旦被救活，这些用例会 XPASS，作为"该把 xfail 摘掉"的信号。
"""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.smoke
def test_engine_api_imports() -> None:
    """引擎主 API 必须可导入。"""

    importlib.import_module("autodoengine.api")


@pytest.mark.smoke
def test_aok_run_affair_imports() -> None:
    """AOK 顶层 `run_affair` 必须可导入（引擎↔kit 存活契约）。"""

    module = importlib.import_module("autodokit")
    assert hasattr(module, "run_affair")


@pytest.mark.smoke
def test_skill_renderer_imports() -> None:
    """`skill_renderer` 必须可导入。

    历史死因 B：jinja2 未声明为依赖。现已补进 `pyproject.toml`，此用例守门。
    """

    importlib.import_module("autodoengine.utils.skill_renderer")


# --- 已知坏死模块（死因 A / C），登记为 xfail，救活后应 XPASS ---

_KNOWN_BROKEN_IMPORTS = [
    ("autodoengine.flow_graph.aof", "死因A：models 重构(Node→GraphNode)误伤，待 P2-1 迁移救活"),
    ("autodoengine.flow_graph.compiler", "死因A：同上，待 P2-1"),
    ("autodoengine.flow_graph.templates", "死因A：同上，且需改读 affair_metadata_overrides.json，待 P2-1/P2-2"),
    ("autodoengine.flow_graph.workflow", "死因A：同上，待 P2-1"),
    ("autodoengine.taskdb.replay_engine", "死因C：state_machine 类→函数重构误伤，待并行·C 类迁移"),
]


@pytest.mark.smoke
@pytest.mark.parametrize("module_name,reason", _KNOWN_BROKEN_IMPORTS)
@pytest.mark.xfail(reason="登记在案的坏死模块，见 reason；救活后应转为通过", strict=False)
def test_known_broken_module_import(module_name: str, reason: str) -> None:
    """尝试导入已知坏死模块。

    Args:
        module_name: 待导入模块名。
        reason: 死因说明（仅作 xfail 记录，不参与断言）。

    当前预期导入失败（xfail）；一旦 P2 / 并行·C 救活，导入成功即 XPASS。
    """

    importlib.import_module(module_name)
