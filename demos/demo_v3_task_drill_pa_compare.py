"""v3 任务事务工作流对照演练脚本（PA 开启 vs 关闭）。"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import autodokit as aok
from autodokit.taskdb import decision_store, list_graphs, log_store, step_store, task_store


def _demo_root() -> Path:
    """返回 demos 根目录。

    Returns:
        demos 根目录绝对路径。
    """

    return Path(r"C:\Users\Ethan\CoreFiles\ProjectsFile\autodo-kit\demos").resolve()


def _graph_file() -> Path:
    """返回最小图文件路径。

    Returns:
        图文件绝对路径。
    """

    return (_demo_root() / "data" / "workflow_v3_min_graph.json").resolve()


def _compare_root() -> Path:
    """返回对照演练目录。

    Returns:
        对照演练根目录绝对路径。
    """

    return (_demo_root() / "output" / "runtime_v3_task_drill_pa_compare").resolve()


def _prepare_runtime(case_name: str) -> Path:
    """准备单组演练运行时目录。

    Args:
        case_name: 演练分组名称。

    Returns:
        运行时目录绝对路径。
    """

    runtime_root = (_compare_root() / case_name).resolve()
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    return runtime_root


def _health_check(task_uid: str, graph_uid: str) -> dict[str, Any]:
    """执行数据库与运行链路健康检查。

    Args:
        task_uid: 任务 UID。
        graph_uid: 图 UID。

    Returns:
        健康检查结果。
    """

    tasks = [task for task in task_store.list_tasks() if task.get("task_uid") == task_uid]
    decisions = decision_store.list_task_decisions(task_uid)
    events = log_store.list_runtime_events(task_uid)
    steps = step_store.list_task_steps(task_uid)
    graphs = list_graphs()

    checks = {
        "task_exists": len(tasks) == 1,
        "graph_registered": any(item.get("graph_uid") == graph_uid for item in graphs),
        "step_count_match_decisions": len(steps) == len(decisions),
        "event_count_match_steps": len(events) == len(steps),
        "final_status_completed": bool(tasks) and tasks[0].get("status") == "completed",
    }
    all_passed = all(checks.values())
    return {
        "checks": checks,
        "all_passed": all_passed,
        "counts": {
            "task_count": len(tasks),
            "graph_count": len(graphs),
            "decision_count": len(decisions),
            "step_count": len(steps),
            "event_count": len(events),
        },
    }


def _run_case(*, case_name: str, disable_pa: bool) -> dict[str, Any]:
    """运行单组对照演练。

    Args:
        case_name: 演练分组名称。
        disable_pa: 是否关闭 PA。

    Returns:
        单组演练结果。
    """

    runtime_root = _prepare_runtime(case_name)
    graph_path = _graph_file()

    aok.bootstrap_runtime(str(runtime_root))
    graph = aok.load_graph(str(graph_path))
    aok.register_graph(graph)

    task = aok.create_task(
        title=f"PA对照演练-{case_name}",
        goal_text="验证 PA 开关对决策与落库行为的影响",
        current_node_uid="node-start",
    )
    task_uid = str(task["task_uid"])

    task_store.update_task_metadata(
        task_uid,
        {
            "workspace_root": str(_demo_root()),
            "disable_pa": disable_pa,
            "disable_node_manager_llm": True,
            "drill_mode": "pa_compare",
            "case_name": case_name,
        },
    )

    decisions = aok.run_task_until_terminal(task_uid=task_uid, graph_uid=graph.graph_uid, max_steps=10)

    final_task = task_store.get_task(task_uid)
    decision_rows = decision_store.list_task_decisions(task_uid)
    event_rows = log_store.list_runtime_events(task_uid)
    step_rows = [asdict(item) for item in step_store.list_task_steps(task_uid)]

    result = {
        "case_name": case_name,
        "disable_pa": disable_pa,
        "runtime_root": str(runtime_root),
        "graph_uid": graph.graph_uid,
        "task_uid": task_uid,
        "final_status": final_task.get("status"),
        "decision_count": len(decisions),
        "decisions": [asdict(item) for item in decisions],
        "decision_rows": decision_rows,
        "step_rows": step_rows,
        "event_count": len(event_rows),
        "events": event_rows,
    }
    result["health"] = _health_check(task_uid=task_uid, graph_uid=graph.graph_uid)
    return result


def _build_compare_summary(pa_on: dict[str, Any], pa_off: dict[str, Any]) -> dict[str, Any]:
    """构建对照摘要。

    Args:
        pa_on: PA 开启组结果。
        pa_off: PA 关闭组结果。

    Returns:
        对照摘要。
    """

    pa_on_reason_codes = [item.get("reason_code") for item in pa_on.get("decisions", [])]
    pa_off_reason_codes = [item.get("reason_code") for item in pa_off.get("decisions", [])]
    pa_on_actions = [item.get("selected_action") for item in pa_on.get("decisions", [])]
    pa_off_actions = [item.get("selected_action") for item in pa_off.get("decisions", [])]

    return {
        "same_final_status": pa_on.get("final_status") == pa_off.get("final_status"),
        "same_action_sequence": pa_on_actions == pa_off_actions,
        "same_step_count": len(pa_on.get("step_rows", [])) == len(pa_off.get("step_rows", [])),
        "same_event_count": pa_on.get("event_count") == pa_off.get("event_count"),
        "pa_on_reason_codes": pa_on_reason_codes,
        "pa_off_reason_codes": pa_off_reason_codes,
        "reason_code_diff": {
            "pa_on_unique": sorted(set(pa_on_reason_codes) - set(pa_off_reason_codes)),
            "pa_off_unique": sorted(set(pa_off_reason_codes) - set(pa_on_reason_codes)),
        },
        "health_all_passed": {
            "pa_on": bool((pa_on.get("health") or {}).get("all_passed")),
            "pa_off": bool((pa_off.get("health") or {}).get("all_passed")),
        },
    }


def _render_markdown_report(report: dict[str, Any]) -> str:
    """渲染 Markdown 对照报告。

    Args:
        report: 对照报告对象。

    Returns:
        Markdown 文本。
    """

    pa_on = report["pa_on"]
    pa_off = report["pa_off"]
    compare = report["compare"]

    lines = [
        "# PA 开启 vs 关闭 对照演练报告",
        "",
        "## 1. 结论摘要",
        f"- PA 开启最终状态：`{pa_on['final_status']}`",
        f"- PA 关闭最终状态：`{pa_off['final_status']}`",
        f"- 动作序列是否一致：`{compare['same_action_sequence']}`",
        f"- 两组健康检查是否全部通过：PA 开启=`{compare['health_all_passed']['pa_on']}`，PA 关闭=`{compare['health_all_passed']['pa_off']}`",
        "",
        "## 2. 决策原因码对照",
        f"- PA 开启原因码：`{compare['pa_on_reason_codes']}`",
        f"- PA 关闭原因码：`{compare['pa_off_reason_codes']}`",
        f"- 原因码差异：`{compare['reason_code_diff']}`",
        "",
        "## 3. 日志与数据库健康检查",
        "- 检查项：任务存在、图已注册、步数=决策数、事件数=步数、任务终态 completed",
        f"- PA 开启检查：`{pa_on['health']}`",
        f"- PA 关闭检查：`{pa_off['health']}`",
        "",
        "## 4. 运行产物路径",
        f"- PA 开启运行时目录：`{pa_on['runtime_root']}`",
        f"- PA 关闭运行时目录：`{pa_off['runtime_root']}`",
        f"- JSON 报告：`{report['json_report_path']}`",
    ]
    return "\n".join(lines) + "\n"


def run_compare_drill() -> dict[str, Any]:
    """执行 PA 开启/关闭对照演练并生成报告。

    Returns:
        完整对照报告对象。
    """

    pa_on = _run_case(case_name="pa_on", disable_pa=False)
    pa_off = _run_case(case_name="pa_off", disable_pa=True)

    compare = _build_compare_summary(pa_on=pa_on, pa_off=pa_off)
    report_root = _compare_root()
    report_root.mkdir(parents=True, exist_ok=True)

    json_report_path = (report_root / "pa_compare_report.json").resolve()
    md_report_path = (report_root / "pa_compare_report.md").resolve()

    report = {
        "report_name": "pa_on_vs_off_compare",
        "pa_on": pa_on,
        "pa_off": pa_off,
        "compare": compare,
        "json_report_path": str(json_report_path),
        "md_report_path": str(md_report_path),
    }

    json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    markdown = _render_markdown_report(report)
    md_report_path.write_text(markdown, encoding="utf-8")
    return report


def main() -> None:
    """脚本入口。"""

    report = run_compare_drill()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
