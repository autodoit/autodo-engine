"""静态图与类型注册表。"""

from __future__ import annotations

import json
from dataclasses import asdict

from autodoengine.flow_graph.models import Graph
from autodoengine.flow_graph.graph_loader import load_graph_from_dict
from .storage_paths import resolve_store_file


def _load_json(name: str) -> list[dict[str, object]]:
    file_path = resolve_store_file(kind="graph_registry", name=name)
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save_json(name: str, rows: list[dict[str, object]]) -> None:
    file_path = resolve_store_file(kind="graph_registry", name=name)
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def register_graph(graph: Graph) -> None:
    """注册静态图。"""

    rows = [row for row in _load_json("graphs.json") if row["graph_uid"] != graph.graph_uid]
    rows.append(
        {
            "graph_uid": graph.graph_uid,
            "graph_name": graph.graph_name,
            "graph_version": graph.graph_version,
            "graph_payload": asdict(graph),
        }
    )
    _save_json("graphs.json", rows)


def get_graph(graph_uid: str) -> Graph:
    """读取静态图。"""

    for row in _load_json("graphs.json"):
        if row["graph_uid"] == graph_uid:
            payload = row["graph_payload"]
            return load_graph_from_dict(payload)
    raise KeyError(f"图不存在：{graph_uid}")


def list_graphs() -> list[dict[str, object]]:
    """列出全部图。"""

    return _load_json("graphs.json")


def register_type(type_kind: str, type_name: str, schema_ref: str | None = None) -> None:
    """注册类型。"""

    rows = _load_json("types.json")
    rows.append(
        {
            "type_uid": f"{type_kind}:{type_name}",
            "type_kind": type_kind,
            "type_name": type_name,
            "schema_ref": schema_ref,
        }
    )
    _save_json("types.json", rows)


def get_type(type_uid: str) -> dict[str, object]:
    """读取类型注册信息。"""

    for row in _load_json("types.json"):
        if row["type_uid"] == type_uid:
            return row
    raise KeyError(f"类型不存在：{type_uid}")


def validate_registered_affair(affair_uid: str) -> bool:
    """校验事务是否已注册。"""

    rows = _load_json("types.json")
    return any(row["type_kind"] == "affair" and row["type_name"] == affair_uid for row in rows)

