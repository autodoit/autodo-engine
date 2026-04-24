"""静态图与类型注册表（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from autodoengine.flow_graph.models import Graph
from autodoengine.flow_graph.graph_loader import load_graph_from_dict
from .storage_paths import get_runtime_store_files


def _get_db_path() -> str:
    return str(get_runtime_store_files()["graph_registry_db"])

def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS graphs (
            graph_uid TEXT PRIMARY KEY,
            graph_name TEXT NOT NULL,
            graph_version TEXT NOT NULL,
            graph_payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS types (
            type_uid TEXT PRIMARY KEY,
            type_kind TEXT NOT NULL,
            type_name TEXT NOT NULL,
            schema_ref TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def register_graph(graph: Graph) -> None:
    """注册静态图。"""

    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO graphs (
                graph_uid, graph_name, graph_version, graph_payload_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                graph.graph_uid,
                graph.graph_name,
                graph.graph_version,
                json.dumps(asdict(graph), ensure_ascii=False),
            ),
        )


def get_graph(graph_uid: str) -> Graph:
    """读取静态图。"""

    with _connect() as connection:
        row = connection.execute("SELECT graph_payload_json FROM graphs WHERE graph_uid=?", (graph_uid,)).fetchone()
    if row is not None:
        payload = json.loads(str(row["graph_payload_json"]))
        return load_graph_from_dict(payload)
    raise KeyError(f"图不存在：{graph_uid}")


def list_graphs() -> list[dict[str, object]]:
    """列出全部图。"""

    with _connect() as connection:
        rows = connection.execute("SELECT graph_uid, graph_name, graph_version, graph_payload_json FROM graphs").fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        result.append(
            {
                "graph_uid": str(row["graph_uid"]),
                "graph_name": str(row["graph_name"]),
                "graph_version": str(row["graph_version"]),
                "graph_payload": json.loads(str(row["graph_payload_json"])),
            }
        )
    return result


def register_type(type_kind: str, type_name: str, schema_ref: str | None = None) -> None:
    """注册类型。"""

    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO types (type_uid, type_kind, type_name, schema_ref)
            VALUES (?, ?, ?, ?)
            """,
            (f"{type_kind}:{type_name}", type_kind, type_name, schema_ref),
        )


def get_type(type_uid: str) -> dict[str, object]:
    """读取类型注册信息。"""

    with _connect() as connection:
        row = connection.execute(
            "SELECT type_uid, type_kind, type_name, schema_ref FROM types WHERE type_uid=?",
            (type_uid,),
        ).fetchone()
    if row is not None:
        return {
            "type_uid": str(row["type_uid"]),
            "type_kind": str(row["type_kind"]),
            "type_name": str(row["type_name"]),
            "schema_ref": row["schema_ref"],
        }
    raise KeyError(f"类型不存在：{type_uid}")


def validate_registered_affair(affair_uid: str) -> bool:
    """校验事务是否已注册。"""

    with _connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM types WHERE type_kind='affair' AND type_name=? LIMIT 1",
            (affair_uid,),
        ).fetchone()
    return row is not None

