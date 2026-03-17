"""把平铺事务脚本迁移为三文件目录结构。

目标结构：
- autodokit/affairs/<affair_name>/affair.py
- autodokit/affairs/<affair_name>/affair.json
- autodokit/affairs/<affair_name>/affair.md

说明：
- 本脚本支持重复执行（幂等）；
- 默认会原地写入并删除旧平铺 `*.py` 文件；
- 如需预览可使用 `--dry-run`。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from autodoengine.utils.path_tools import find_repo_root


GRAPH_NODE_NAME_MAP: Dict[str, str] = {
    "graph_node_start": "图节点_start",
    "graph_node_end": "图节点_end",
    "graph_node_if": "图节点_if",
    "graph_node_fork": "图节点_fork",
    "graph_node_container": "图节点_container",
    "graph_node_input": "图节点_input",
    "graph_node_output": "图节点_output",
    "graph_node_calc": "图节点_calc",
    "graph_node_compare": "图节点_compare",
    "graph_node_switch": "图节点_switch",
    "graph_node_merge": "图节点_merge",
}


def _repo_root() -> Path:
    """返回仓库根目录。"""

    return find_repo_root(Path(__file__))


def _affairs_root() -> Path:
    """返回事务目录根路径。

    Returns:
        `autodokit/affairs` 绝对路径。
    """

    return (_repo_root() / "autodokit" / "affairs").resolve()


def _target_affair_name(stem: str) -> str:
    """将旧模块名映射为新事务名。

    Args:
        stem: 旧 `*.py` 文件名（不含后缀）。

    Returns:
        目标事务名。
    """

    return GRAPH_NODE_NAME_MAP.get(stem, stem)


def _manifest_for(affair_name: str, old_module_stem: str) -> Dict[str, object]:
    """构造默认 affair.json。

    Args:
        affair_name: 事务名。
        old_module_stem: 旧模块名。

    Returns:
        事务元数据字典。
    """

    module_path = f"autodoengine.affairs.{affair_name}.affair"
    legacy_aliases = [f"autodoengine.affairs.{old_module_stem}"]
    return {
        "name": affair_name,
        "version": "1.0.0",
        "description": f"事务 {affair_name}",
        "tags": [],
        "docs": {
            "md_path": f"autodokit/affairs/{affair_name}/affair.md",
        },
        "runner": {
            "module": module_path,
            "callable": "execute",
            "pass_mode": "config_path",
            "kwargs": {},
        },
        "interface": {
            "inputs": [],
            "outputs": [],
        },
        "config": {
            "defaults": {},
            "required": [],
        },
        "legacy": {
            "module_aliases": legacy_aliases,
        },
    }


def _doc_template(affair_name: str) -> str:
    """生成默认 affair.md 内容。

    Args:
        affair_name: 事务名。

    Returns:
        Markdown 文本。
    """

    return (
        f"# {affair_name}\n\n"
        "## 用途\n\n"
        f"- 该事务用于执行 `{affair_name}` 对应的业务逻辑。\n\n"
        "## 运行入口\n\n"
        "- module: `autodokit.affairs.<affair_name>.affair`\n"
        "- callable: `execute`\n"
        "- pass_mode: `config_path`\n\n"
        "## 参数说明\n\n"
        "- 以 `affair.json.interface.inputs` 与代码实现为准。\n\n"
        "## 输出说明\n\n"
        "- 以 `affair.json.interface.outputs` 与运行日志为准。\n"
    )


def migrate_affairs(*, dry_run: bool = False) -> Tuple[List[str], List[str], List[str]]:
    """执行事务目录迁移。

    Args:
        dry_run: 是否仅预览，不落盘。

    Returns:
        (success, skipped, failed) 三个列表。
    """

    root = _affairs_root()
    success: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []

    if not root.exists():
        return success, skipped, [f"事务目录不存在：{root}"]

    for py_file in sorted(root.glob("*.py")):
        if py_file.name == "__init__.py":
            continue

        old_stem = py_file.stem
        affair_name = _target_affair_name(old_stem)
        target_dir = (root / affair_name).resolve()
        target_py = (target_dir / "affair.py").resolve()
        target_json = (target_dir / "affair.json").resolve()
        target_md = (target_dir / "affair.md").resolve()
        target_init = (target_dir / "__init__.py").resolve()

        try:
            if target_dir.exists() and target_py.exists() and target_json.exists() and target_md.exists():
                skipped.append(f"{old_stem} -> {affair_name}（已存在）")
                if not dry_run and py_file.exists():
                    py_file.unlink()
                continue

            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(py_file, target_py)
                target_json.write_text(
                    json.dumps(_manifest_for(affair_name, old_stem), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                target_md.write_text(_doc_template(affair_name), encoding="utf-8")
                target_init.write_text(
                    '"""事务包入口。"""\n\nfrom .affair import execute\n\n__all__ = ["execute"]\n',
                    encoding="utf-8",
                )
                py_file.unlink()

            success.append(f"{old_stem} -> {affair_name}")
        except Exception as exc:
            failed.append(f"{old_stem} -> {affair_name} 失败：{exc}")

    return success, skipped, failed


def main() -> None:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="迁移平铺事务为目录结构")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    args = parser.parse_args()

    success, skipped, failed = migrate_affairs(dry_run=args.dry_run)

    print("\n=== 迁移结果 ===")
    print(f"成功：{len(success)}")
    print(f"跳过：{len(skipped)}")
    print(f"失败：{len(failed)}")

    if success:
        print("\n[成功项]")
        for item in success:
            print(f"- {item}")
    if skipped:
        print("\n[跳过项]")
        for item in skipped:
            print(f"- {item}")
    if failed:
        print("\n[失败项]")
        for item in failed:
            print(f"- {item}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

