"""静态图与类型注册表（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
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
        CREATE TABLE IF NOT EXISTS "图注册表" (
            uid_图 TEXT PRIMARY KEY,
            图名称 TEXT NOT NULL,
            图版本 TEXT NOT NULL,
            图载荷JSON TEXT NOT NULL,
            创建时间 TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "类型注册表" (
            uid_类型 TEXT PRIMARY KEY,
            类型类别 TEXT NOT NULL,
            类型名称 TEXT NOT NULL,
            Schema引用 TEXT,
            创建时间 TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def register_graph(graph: Graph) -> None:
    """注册静态图。"""

    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO "图注册表" (
                uid_图, 图名称, 图版本, 图载荷JSON
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

    with closing(_connect()) as connection, connection:
        row = connection.execute("SELECT 图载荷JSON FROM \"图注册表\" WHERE uid_图=?", (graph_uid,)).fetchone()
    if row is not None:
        payload = json.loads(str(row["图载荷JSON"]))
        return load_graph_from_dict(payload)
    raise KeyError(f"图不存在：{graph_uid}")


def list_graphs() -> list[dict[str, object]]:
    """列出全部图。"""

    with closing(_connect()) as connection, connection:
        rows = connection.execute("SELECT uid_图, 图名称, 图版本, 图载荷JSON FROM \"图注册表\"").fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        graph_payload = json.loads(str(row["图载荷JSON"]))
        result.append(
            {
                "uid_图": str(row["uid_图"]),
                "图名称": str(row["图名称"]),
                "图版本": str(row["图版本"]),
                "图载荷": graph_payload,
                "graph_uid": str(row["uid_图"]),
                "graph_name": str(row["图名称"]),
                "graph_version": str(row["图版本"]),
                "graph_payload": graph_payload,
            }
        )
    return result


def register_type(type_kind: str, type_name: str, schema_ref: str | None = None) -> None:
    """注册类型。"""

    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO "类型注册表" (uid_类型, 类型类别, 类型名称, Schema引用)
            VALUES (?, ?, ?, ?)
            """,
            (f"{type_kind}:{type_name}", type_kind, type_name, schema_ref),
        )


def get_type(type_uid: str) -> dict[str, object]:
    """读取类型注册信息。"""

    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT uid_类型, 类型类别, 类型名称, Schema引用 FROM \"类型注册表\" WHERE uid_类型=?",
            (type_uid,),
        ).fetchone()
    if row is not None:
        return {
            "uid_类型": str(row["uid_类型"]),
            "类型类别": str(row["类型类别"]),
            "类型名称": str(row["类型名称"]),
            "Schema引用": row["Schema引用"],
            "type_uid": str(row["uid_类型"]),
            "type_kind": str(row["类型类别"]),
            "type_name": str(row["类型名称"]),
            "schema_ref": row["Schema引用"],
        }
    raise KeyError(f"类型不存在：{type_uid}")


def validate_registered_affair(affair_uid: str) -> bool:
    """校验事务是否已注册。"""

    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT 1 FROM \"类型注册表\" WHERE 类型类别='affair' AND 类型名称=? LIMIT 1",
            (affair_uid,),
        ).fetchone()
    return row is not None

