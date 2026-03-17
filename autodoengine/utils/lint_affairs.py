"""事务目录结构与 runner 校验命令。"""

from __future__ import annotations

import argparse
from pathlib import Path

from autodoengine.utils.affair_registry import lint_affairs
from autodoengine.utils.path_tools import resolve_path_from_base


def main() -> None:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="校验 autodokit/affairs 事务目录")
    parser.add_argument(
        "--root",
        type=str,
        default="",
        help="事务根目录，默认 autodokit/affairs",
    )
    parser.add_argument(
        "--skip-import-check",
        action="store_true",
        help="跳过 runner 模块导入校验",
    )
    args = parser.parse_args()

    root = resolve_path_from_base(args.root, base_dir=Path.cwd()) if args.root.strip() else None
    result = lint_affairs(root=root, check_import=not args.skip_import_check)

    print(f"扫描事务数：{result.scanned_count}")
    print(f"通过：{result.passed}")

    if result.warnings:
        print("\n[警告]")
        for item in result.warnings:
            print(f"- {item}")

    if result.errors:
        print("\n[错误]")
        for item in result.errors:
            print(f"- {item}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

