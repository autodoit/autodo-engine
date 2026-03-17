"""v3 命令行入口。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from autodoengine import api
from autodoengine.taskdb import decision_store, log_store, task_store


def _to_jsonable(value: object) -> object:
    """将 CLI 输出值转换为 JSON 兼容对象。"""

    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。"""

    parser = argparse.ArgumentParser(description="AOK v3 任务事务工作流 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-runtime", help="初始化运行时存储")
    p_init.add_argument("--base-dir", required=True, help="运行时根目录")

    p_register = sub.add_parser("register-graph", help="注册静态图")
    p_register.add_argument("--graph-file", required=True, help="图文件路径")

    p_create = sub.add_parser("create-task", help="创建任务")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--goal-text", required=True)
    p_create.add_argument("--current-node-uid", required=True)
    p_create.add_argument("--parent-task-uid", default=None)

    p_step = sub.add_parser("run-task-step", help="执行单步")
    p_step.add_argument("--task-uid", required=True)
    p_step.add_argument("--graph-uid", required=True)

    p_run = sub.add_parser("run-task", help="持续运行直到等待态")
    p_run.add_argument("--task-uid", required=True)
    p_run.add_argument("--graph-uid", required=True)
    p_run.add_argument("--max-steps", type=int, default=100)

    p_show_task = sub.add_parser("show-task", help="查看任务")
    p_show_task.add_argument("--task-uid", required=True)

    p_show_decisions = sub.add_parser("show-decisions", help="查看任务决策")
    p_show_decisions.add_argument("--task-uid", required=True)

    p_show_events = sub.add_parser("show-runtime-events", help="查看运行事件")
    p_show_events.add_argument("--task-uid", default=None)

    p_refresh_affairs = sub.add_parser("refresh-affair-registry", help="刷新事务数据库")
    p_refresh_affairs.add_argument("--workspace-root", default=None, help="用户工作区根目录")
    p_refresh_affairs.add_argument("--strict", action="store_true", help="严格模式（有错误即失败）")

    p_list_affairs = sub.add_parser("list-runtime-affairs", help="查看运行时事务列表")
    p_list_affairs.add_argument("--workspace-root", default=None, help="用户工作区根目录")
    p_list_affairs.add_argument("--strict", action="store_true", help="严格模式（有错误即失败）")

    p_check_conflicts = sub.add_parser("check-affair-conflicts", help="检查事务冲突与告警")
    p_check_conflicts.add_argument("--workspace-root", default=None, help="用户工作区根目录")

    p_show_runtime_paths = sub.add_parser("show-runtime-store-paths", help="查看当前运行时数据库路径")
    p_show_runtime_paths.add_argument("--base-dir", default=None, help="运行时根目录；不传时读取当前进程已初始化的运行时")

    p_show_affair_paths = sub.add_parser("show-affair-registry-paths", help="查看事务管理系统路径")
    p_show_affair_paths.add_argument("--workspace-root", default=None, help="用户工作区根目录")

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """运行命令行入口。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-runtime":
        api.bootstrap_runtime(args.base_dir)
        print(f"已初始化运行时：{Path(args.base_dir).resolve()}")
        return 0

    if args.command == "register-graph":
        graph = api.load_graph(args.graph_file)
        api.register_graph(graph)
        print(f"已注册图：{graph.graph_uid}")
        return 0

    if args.command == "create-task":
        task = api.create_task(
            title=args.title,
            goal_text=args.goal_text,
            current_node_uid=args.current_node_uid,
            parent_task_uid=args.parent_task_uid,
        )
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-task-step":
        result = api.run_task_step(task_uid=args.task_uid, graph_uid=args.graph_uid)
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "run-task":
        results = api.run_task_until_wait(
            task_uid=args.task_uid,
            graph_uid=args.graph_uid,
            max_steps=args.max_steps,
        )
        payload = [_to_jsonable(item) for item in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-task":
        task = task_store.get_task(args.task_uid)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.command == "show-decisions":
        rows = decision_store.list_task_decisions(args.task_uid)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-runtime-events":
        rows = log_store.list_runtime_events(args.task_uid)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "refresh-affair-registry":
        payload = api.refresh_affair_registry(workspace_root=args.workspace_root, strict=bool(args.strict))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "list-runtime-affairs":
        rows = api.list_runtime_affairs(workspace_root=args.workspace_root, strict=bool(args.strict))
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "check-affair-conflicts":
        payload = api.check_affair_conflicts(workspace_root=args.workspace_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-runtime-store-paths":
        payload = api.get_runtime_store_paths(base_dir=args.base_dir)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "show-affair-registry-paths":
        payload = api.get_affair_registry_paths(workspace_root=args.workspace_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    parser.print_help()
    return 1


def main() -> int:
    """CLI 主函数。"""

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())

