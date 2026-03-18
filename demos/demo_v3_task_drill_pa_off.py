"""v3 任务事务工作流演练脚本（关闭 PA / 节点管理 LLM）。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import autodokit as aok
from autodokit.taskdb import decision_store, log_store, task_store


def _demo_root() -> Path:
    """返回 demos 根目录。

    Returns:
        demos 根目录绝对路径。
    """

    return Path(r"C:\Users\Ethan\CoreFiles\ProjectsFile\autodo-kit\demos").resolve()


def _runtime_root() -> Path:
    """返回演练运行时目录。

    Returns:
        运行时目录绝对路径。
    """

    return (_demo_root() / "output" / "runtime_v3_task_drill_pa_off").resolve()


def _graph_file() -> Path:
    """返回最小图文件路径。

    Returns:
        图文件绝对路径。
    """

    return (_demo_root() / "data" / "workflow_v3_min_graph.json").resolve()


def run_drill() -> dict[str, object]:
    """执行一次 v3 演练。

    演练策略：
    1. 暂时关闭 PA（`disable_pa=True`）。
    2. 暂时关闭节点管理 LLM（`disable_node_manager_llm=True`，用于治理标识）。
    3. 业务事务若内部调用 LLM，不做拦截。

    Returns:
        演练结果摘要。
    """

    runtime = _runtime_root()
    graph_path = _graph_file()

    aok.bootstrap_runtime(str(runtime))
    graph = aok.load_graph(str(graph_path))
    aok.register_graph(graph)

    task = aok.create_task(
        title="PA关闭演练任务",
        goal_text="在无 PA 裁决时按推荐动作推进任务",
        current_node_uid="node-start",
    )
    task_uid = str(task["task_uid"])

    task_store.update_task_metadata(
        task_uid,
        {
            "workspace_root": str(_demo_root()),
            "disable_pa": True,
            "disable_node_manager_llm": True,
            "drill_mode": "pa_off",
        },
    )

    decisions = aok.run_task_until_terminal(task_uid=task_uid, graph_uid=graph.graph_uid, max_steps=10)

    final_task = task_store.get_task(task_uid)
    decision_rows = decision_store.list_task_decisions(task_uid)
    event_rows = log_store.list_runtime_events(task_uid)

    summary = {
        "runtime_root": str(runtime),
        "graph_uid": graph.graph_uid,
        "task_uid": task_uid,
        "final_status": final_task.get("status"),
        "decision_count": len(decisions),
        "decisions": [asdict(item) for item in decisions],
        "decision_rows": decision_rows,
        "event_count": len(event_rows),
        "events": event_rows,
    }

    report_path = runtime / "drill_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary["report_path"] = str(report_path)
    return summary


def main() -> None:
    """脚本入口。"""

    result = run_drill()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
