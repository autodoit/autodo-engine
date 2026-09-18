"""引擎冒烟测试（CI 必跑门）。

目标：把"引擎能不能被导入、关键存活契约在不在"变成秒级可判定的门，
避免像历史上那样"断裂潜伏半年无人发现"。

覆盖：
- 引擎主 API、AOK `run_affair`、依赖修复后的 `skill_renderer`。
- P2 已救活的历史坏死模块：V2 前端四模块（workflow/templates/compiler/aof，原死因 A）
  与 `taskdb.replay_engine`（原死因 C）。这些曾长期零引用零测试，现由本门守活。
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


@pytest.mark.smoke
@pytest.mark.parametrize(
    "module_name",
    [
        "autodoengine.flow_graph.workflow",
        "autodoengine.flow_graph.templates",
        "autodoengine.flow_graph.compiler",
        "autodoengine.flow_graph.aof",
        "autodoengine.taskdb.replay_engine",
    ],
)
def test_rescued_modules_import(module_name: str) -> None:
    """P2 已救活的历史坏死模块必须稳定可导入（原死因 A / B / C）。"""

    importlib.import_module(module_name)
