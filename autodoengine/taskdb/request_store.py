"""事务请求存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files

请求状态_待调度 = "待调度"
请求状态_待租约 = "待租约"
请求状态_已租约 = "已租约"
请求状态_执行中 = "执行中"
请求状态_待提交 = "待提交"
请求状态_已提交 = "已提交"
请求状态_已完成 = "已完成"
请求状态_已阻断 = "已阻断"
请求状态_已失败 = "已失败"
请求状态_已取消 = "已取消"

租约状态_已持有 = "已持有"
租约状态_已释放 = "已释放"
租约状态_已过期 = "已过期"
租约状态_已完成 = "已完成"
租约状态_已失败 = "已失败"

执行者状态_空闲 = "空闲"
执行者状态_忙碌 = "忙碌"
执行者状态_阻断 = "阻断"
执行者状态_离线 = "离线"


def _get_db_path() -> str:
    return str(get_runtime_store_files()["tasks_db"])


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path(), timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=30000;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    _ensure_schema(connection)
    return connection


def _parse_iso_datetime(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromisoformat(now_iso())
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def _add_seconds_iso(base_text: str, seconds: int) -> str:
    base = _parse_iso_datetime(base_text)
    return (base + timedelta(seconds=max(1, int(seconds or 1)))).isoformat()


def _is_expired(expire_text: str, now_text: str) -> bool:
    try:
        return _parse_iso_datetime(expire_text) <= _parse_iso_datetime(now_text)
    except Exception:
        return True


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "事务请求" (
            uid_请求 TEXT PRIMARY KEY,
            uid_任务 TEXT,
            "请求类型" TEXT NOT NULL,
            "来源对象类型" TEXT NOT NULL DEFAULT '',
            "来源对象UID" TEXT NOT NULL DEFAULT '',
            "节点编码" TEXT NOT NULL DEFAULT '',
            "uid_目标事务" TEXT NOT NULL,
            "配置路径" TEXT NOT NULL DEFAULT '',
            "请求状态" TEXT NOT NULL,
            "优先得分" REAL NOT NULL DEFAULT 0,
            "来源" TEXT NOT NULL DEFAULT '',
            "请求契约JSON" TEXT NOT NULL DEFAULT '{}',
            "载荷JSON" TEXT NOT NULL DEFAULT '{}',
            "结果JSON" TEXT NOT NULL DEFAULT '{}',
            "元数据JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "资源租约" (
            uid_租约 TEXT PRIMARY KEY,
            uid_请求 TEXT NOT NULL,
            "uid_执行者" TEXT NOT NULL,
            "资源指纹" TEXT NOT NULL,
            "访问模式" TEXT NOT NULL DEFAULT '写',
            "租约状态" TEXT NOT NULL DEFAULT '已持有',
            "过期时间" TEXT NOT NULL,
            "心跳时间" TEXT NOT NULL,
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "执行者心跳" (
            uid_执行者 TEXT PRIMARY KEY,
            "执行者类型" TEXT NOT NULL DEFAULT 'agent',
            "当前请求UID" TEXT NOT NULL DEFAULT '',
            "运行状态" TEXT NOT NULL DEFAULT '空闲',
            "最近心跳时间" TEXT NOT NULL,
            "元数据JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    _ensure_column(connection, "事务请求", "uid_任务", "TEXT")
    _ensure_column(connection, "事务请求", "请求类型", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "来源对象类型", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "来源对象UID", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "节点编码", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "uid_目标事务", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "配置路径", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "请求状态", "TEXT NOT NULL DEFAULT '待调度'")
    _ensure_column(connection, "事务请求", "优先得分", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "事务请求", "来源", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "请求契约JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "载荷JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "结果JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "元数据JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "创建时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "更新时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "调度状态", "TEXT NOT NULL DEFAULT '待调度'")
    _ensure_column(connection, "事务请求", "uid_执行者", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "资源指纹", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "幂等键", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "预期版本", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "快照令牌", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "租约过期时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "提交状态", "TEXT NOT NULL DEFAULT '未提交'")

    _ensure_column(connection, "资源租约", "uid_请求", "TEXT NOT NULL")
    _ensure_column(connection, "资源租约", "uid_执行者", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "资源租约", "资源指纹", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "资源租约", "访问模式", "TEXT NOT NULL DEFAULT '写'")
    _ensure_column(connection, "资源租约", "租约状态", "TEXT NOT NULL DEFAULT '已持有'")
    _ensure_column(connection, "资源租约", "过期时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "资源租约", "心跳时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "资源租约", "创建时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "资源租约", "更新时间", "TEXT NOT NULL DEFAULT ''")

    _ensure_column(connection, "执行者心跳", "执行者类型", "TEXT NOT NULL DEFAULT 'agent'")
    _ensure_column(connection, "执行者心跳", "当前请求UID", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "执行者心跳", "运行状态", "TEXT NOT NULL DEFAULT '空闲'")
    _ensure_column(connection, "执行者心跳", "最近心跳时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "执行者心跳", "元数据JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "执行者心跳", "创建时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "执行者心跳", "更新时间", "TEXT NOT NULL DEFAULT ''")

    connection.execute(
        'CREATE INDEX IF NOT EXISTS "idx_事务请求_状态优先" ON "事务请求" ("请求状态", "优先得分", "创建时间")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "idx_事务请求_执行者" ON "事务请求" ("uid_执行者", "更新时间")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "idx_资源租约_请求状态" ON "资源租约" (uid_请求, "租约状态", "过期时间")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "idx_执行者心跳_状态" ON "执行者心跳" ("运行状态", "最近心跳时间")'
    )
    connection.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_资源租约_请求_持有" ON "资源租约" (uid_请求) WHERE "租约状态" = "{租约状态_已持有}"'
    )
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name in existing:
        return
    connection.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}')


def _get_request_row(connection: sqlite3.Connection, request_uid: str) -> sqlite3.Row | None:
    return connection.execute('SELECT * FROM "事务请求" WHERE uid_请求=?', (request_uid,)).fetchone()


def _row_to_lease(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "uid_租约": str(payload.get("uid_租约") or ""),
        "lease_uid": str(payload.get("uid_租约") or ""),
        "uid_请求": str(payload.get("uid_请求") or ""),
        "request_uid": str(payload.get("uid_请求") or ""),
        "uid_执行者": str(payload.get("uid_执行者") or ""),
        "executor_uid": str(payload.get("uid_执行者") or ""),
        "资源指纹": str(payload.get("资源指纹") or ""),
        "resource_fingerprint": str(payload.get("资源指纹") or ""),
        "访问模式": str(payload.get("访问模式") or ""),
        "access_mode": str(payload.get("访问模式") or ""),
        "租约状态": str(payload.get("租约状态") or 租约状态_已持有),
        "lease_status": str(payload.get("租约状态") or 租约状态_已持有),
        "过期时间": str(payload.get("过期时间") or ""),
        "expires_at": str(payload.get("过期时间") or ""),
        "心跳时间": str(payload.get("心跳时间") or ""),
        "heartbeat_at": str(payload.get("心跳时间") or ""),
        "创建时间": str(payload.get("创建时间") or ""),
        "created_at": str(payload.get("创建时间") or ""),
        "更新时间": str(payload.get("更新时间") or ""),
        "updated_at": str(payload.get("更新时间") or ""),
    }


def _upsert_executor_heartbeat_internal(
    connection: sqlite3.Connection,
    *,
    executor_uid: str,
    executor_type: str,
    current_request_uid: str,
    status: str,
    metadata: dict[str, Any] | None,
    now_text: str,
) -> None:
    row = connection.execute('SELECT uid_执行者 FROM "执行者心跳" WHERE uid_执行者=?', (executor_uid,)).fetchone()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    if row is None:
        connection.execute(
            'INSERT INTO "执行者心跳" (uid_执行者, "执行者类型", "当前请求UID", "运行状态", "最近心跳时间", "元数据JSON", "创建时间", "更新时间") VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                executor_uid,
                executor_type,
                current_request_uid,
                status,
                now_text,
                metadata_json,
                now_text,
                now_text,
            ),
        )
        return
    connection.execute(
        'UPDATE "执行者心跳" SET "执行者类型"=?, "当前请求UID"=?, "运行状态"=?, "最近心跳时间"=?, "元数据JSON"=?, "更新时间"=? WHERE uid_执行者=?',
        (
            executor_type,
            current_request_uid,
            status,
            now_text,
            metadata_json,
            now_text,
            executor_uid,
        ),
    )


def _cleanup_expired_leases(connection: sqlite3.Connection, *, now_text: str) -> None:
    rows = connection.execute(
        'SELECT uid_租约, uid_请求, "过期时间" FROM "资源租约" WHERE "租约状态"=?',
        (租约状态_已持有,),
    ).fetchall()
    expired_request_uids: set[str] = set()
    for row in rows:
        lease_uid = str(row["uid_租约"])
        request_uid = str(row["uid_请求"])
        expire_text = str(row["过期时间"] or "")
        if not _is_expired(expire_text, now_text):
            continue
        connection.execute(
            'UPDATE "资源租约" SET "租约状态"=?, "更新时间"=? WHERE uid_租约=?',
            (租约状态_已过期, now_text, lease_uid),
        )
        expired_request_uids.add(request_uid)

    for request_uid in expired_request_uids:
        connection.execute(
            'UPDATE "事务请求" SET "请求状态"=?, "调度状态"=?, "uid_执行者"=?, "租约过期时间"=?, "更新时间"=? WHERE uid_请求=? AND "请求状态" IN (?, ?)',
            (
                请求状态_待租约,
                请求状态_待租约,
                "",
                "",
                now_text,
                request_uid,
                请求状态_已租约,
                请求状态_执行中,
            ),
        )


def _resolve_schedule_status(status: str) -> str:
    normalized = str(status or "").strip() or 请求状态_待调度
    if normalized in {
        请求状态_待调度,
        请求状态_待租约,
        请求状态_已租约,
        请求状态_执行中,
        请求状态_待提交,
        请求状态_已提交,
        请求状态_已完成,
        请求状态_已阻断,
        请求状态_已失败,
        请求状态_已取消,
    }:
        return normalized
    return 请求状态_待调度


def _normalize_scheduling_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """归一化调度策略。

    Args:
        policy: 外部传入策略。

    Returns:
        合并默认值后的策略。
    """

    raw = policy if isinstance(policy, dict) else {}
    raw_weights = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}

    return {
        "preselect_multiplier": max(1.0, float(raw.get("preselect_multiplier", 4.0) or 4.0)),
        "min_preselect": max(10, int(raw.get("min_preselect", 40) or 40)),
        "age_cap_minutes": max(1.0, float(raw.get("age_cap_minutes", 240.0) or 240.0)),
        "retry_cap": max(1, int(raw.get("retry_cap", 4) or 4)),
        "executor_stickiness_bonus": float(raw.get("executor_stickiness_bonus", 0.05) or 0.05),
        "weights": {
            "priority": float(raw_weights.get("priority", 0.55) or 0.55),
            "age": float(raw_weights.get("age", 0.30) or 0.30),
            "retry_penalty": float(raw_weights.get("retry_penalty", 0.10) or 0.10),
            "source_penalty": float(raw_weights.get("source_penalty", 0.05) or 0.05),
        },
    }


def _extract_retry_count(request_row: dict[str, Any]) -> int:
    """从请求行提取重试次数。"""

    metadata_raw = request_row.get("元数据JSON")
    if isinstance(metadata_raw, str):
        try:
            metadata_obj = json.loads(metadata_raw or "{}")
        except Exception:
            metadata_obj = {}
    elif isinstance(metadata_raw, dict):
        metadata_obj = metadata_raw
    else:
        metadata_obj = {}

    for key in ["retry_count", "attempt_count", "重试次数", "尝试次数"]:
        value = metadata_obj.get(key)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except Exception:
            continue
    return 0


def _collect_schedulable_rows(
    connection: sqlite3.Connection,
    *,
    statuses: list[str],
    now_text: str,
    fetch_limit: int,
) -> list[dict[str, Any]]:
    """读取候选请求行。"""

    placeholder = ",".join(["?"] * len(statuses))
    sql = f'''
        SELECT r.*
        FROM "事务请求" r
        WHERE r."请求状态" IN ({placeholder})
          AND NOT EXISTS (
                SELECT 1
                FROM "资源租约" l
                WHERE l.uid_请求 = r.uid_请求
                  AND l."租约状态" = ?
                  AND l."过期时间" > ?
          )
        ORDER BY r."创建时间" ASC
        LIMIT ?
    '''
    rows = connection.execute(
        sql,
        (*statuses, 租约状态_已持有, now_text, max(1, int(fetch_limit or 1))),
    ).fetchall()
    return [dict(row) for row in rows]


def _score_schedulable_rows(
    rows: list[dict[str, Any]],
    *,
    now_text: str,
    policy: dict[str, Any],
    executor_uid: str = "",
) -> list[dict[str, Any]]:
    """对候选请求行打分并排序。"""

    if not rows:
        return []

    weights = policy.get("weights") if isinstance(policy.get("weights"), dict) else {}
    weight_priority = float(weights.get("priority", 0.55) or 0.55)
    weight_age = float(weights.get("age", 0.30) or 0.30)
    weight_retry_penalty = float(weights.get("retry_penalty", 0.10) or 0.10)
    weight_source_penalty = float(weights.get("source_penalty", 0.05) or 0.05)

    age_cap_minutes = max(1.0, float(policy.get("age_cap_minutes", 240.0) or 240.0))
    retry_cap = max(1, int(policy.get("retry_cap", 4) or 4))
    stickiness_bonus = float(policy.get("executor_stickiness_bonus", 0.05) or 0.05)

    priority_values = [float(item.get("优先得分") or 0.0) for item in rows]
    priority_min = min(priority_values)
    priority_max = max(priority_values)
    priority_span = max(1e-9, priority_max - priority_min)

    source_counter: dict[str, int] = {}
    for row in rows:
        source_key = str(row.get("来源") or row.get("来源对象类型") or "")
        source_counter[source_key] = source_counter.get(source_key, 0) + 1
    max_source_count = max(source_counter.values()) if source_counter else 1

    scored_rows: list[dict[str, Any]] = []
    now_dt = _parse_iso_datetime(now_text)
    normalized_executor_uid = str(executor_uid or "").strip()

    for row in rows:
        priority_raw = float(row.get("优先得分") or 0.0)
        priority_norm = (priority_raw - priority_min) / priority_span

        created_at_text = str(row.get("创建时间") or now_text)
        try:
            wait_seconds = max(0.0, (now_dt - _parse_iso_datetime(created_at_text)).total_seconds())
        except Exception:
            wait_seconds = 0.0
        age_norm = min(1.0, (wait_seconds / 60.0) / age_cap_minutes)

        retry_count = _extract_retry_count(row)
        retry_norm = min(1.0, float(retry_count) / float(retry_cap))

        source_key = str(row.get("来源") or row.get("来源对象类型") or "")
        source_pressure_norm = float(source_counter.get(source_key, 1)) / float(max_source_count)

        sticky = 0.0
        if normalized_executor_uid and normalized_executor_uid == str(row.get("uid_执行者") or ""):
            sticky = stickiness_bonus

        schedule_score = (
            weight_priority * priority_norm
            + weight_age * age_norm
            - weight_retry_penalty * retry_norm
            - weight_source_penalty * source_pressure_norm
            + sticky
        )

        enriched = dict(row)
        enriched["__schedule_score__"] = float(schedule_score)
        enriched["__schedule_breakdown__"] = {
            "priority_norm": priority_norm,
            "age_norm": age_norm,
            "retry_norm": retry_norm,
            "source_pressure_norm": source_pressure_norm,
            "sticky_bonus": sticky,
            "retry_count": retry_count,
        }
        scored_rows.append(enriched)

    scored_rows.sort(
        key=lambda item: (
            -float(item.get("__schedule_score__") or 0.0),
            -float(item.get("优先得分") or 0.0),
            str(item.get("创建时间") or ""),
        )
    )
    return scored_rows


def _row_to_request(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        body = json.loads(str(payload.get("载荷JSON") or "{}"))
    except Exception:
        body = {}
    try:
        result = json.loads(str(payload.get("结果JSON") or "{}"))
    except Exception:
        result = {}
    try:
        metadata = json.loads(str(payload.get("元数据JSON") or "{}"))
    except Exception:
        metadata = {}
    try:
        request_contract = json.loads(str(payload.get("请求契约JSON") or "{}"))
    except Exception:
        request_contract = {}
    result = {
        "uid_请求": str(payload.get("uid_请求") or ""),
        "request_uid": str(payload.get("uid_请求") or ""),
        "uid_任务": str(payload.get("uid_任务") or ""),
        "task_uid": str(payload.get("uid_任务") or ""),
        "request_type": str(payload.get("请求类型") or ""),
        "source_object_type": str(payload.get("来源对象类型") or ""),
        "来源对象类型": str(payload.get("来源对象类型") or ""),
        "source_object_uid": str(payload.get("来源对象UID") or ""),
        "来源对象UID": str(payload.get("来源对象UID") or ""),
        "node_code": str(payload.get("节点编码") or ""),
        "节点编码": str(payload.get("节点编码") or ""),
        "target_affair_uid": str(payload.get("uid_目标事务") or ""),
        "config_path": str(payload.get("配置路径") or ""),
        "配置路径": str(payload.get("配置路径") or ""),
        "status": str(payload.get("请求状态") or 请求状态_待调度),
        "请求状态": str(payload.get("请求状态") or 请求状态_待调度),
        "调度状态": str(payload.get("调度状态") or payload.get("请求状态") or 请求状态_待调度),
        "priority_score": float(payload.get("优先得分") or 0),
        "source": str(payload.get("来源") or ""),
        "request_contract": request_contract if isinstance(request_contract, dict) else {},
        "请求契约": request_contract if isinstance(request_contract, dict) else {},
        "payload": body if isinstance(body, dict) else {},
        "result": result if isinstance(result, dict) else {},
        "metadata": metadata if isinstance(metadata, dict) else {},
        "uid_执行者": str(payload.get("uid_执行者") or ""),
        "executor_uid": str(payload.get("uid_执行者") or ""),
        "资源指纹": str(payload.get("资源指纹") or ""),
        "resource_fingerprint": str(payload.get("资源指纹") or ""),
        "幂等键": str(payload.get("幂等键") or ""),
        "idempotency_key": str(payload.get("幂等键") or ""),
        "预期版本": str(payload.get("预期版本") or ""),
        "expected_version": str(payload.get("预期版本") or ""),
        "快照令牌": str(payload.get("快照令牌") or ""),
        "snapshot_token": str(payload.get("快照令牌") or ""),
        "租约过期时间": str(payload.get("租约过期时间") or ""),
        "lease_expire_at": str(payload.get("租约过期时间") or ""),
        "提交状态": str(payload.get("提交状态") or "未提交"),
        "commit_status": str(payload.get("提交状态") or "未提交"),
        "created_at": str(payload.get("创建时间") or ""),
        "updated_at": str(payload.get("更新时间") or ""),
    }
    if "__schedule_score__" in payload:
        result["schedule_score"] = float(payload.get("__schedule_score__") or 0.0)
    if "__schedule_breakdown__" in payload:
        breakdown = payload.get("__schedule_breakdown__")
        result["schedule_breakdown"] = breakdown if isinstance(breakdown, dict) else {}
    return result


def create_request(
    *,
    request_type: str,
    target_affair_uid: str,
    payload: dict[str, Any] | None = None,
    task_uid: str | None = None,
    source_object_type: str = "",
    source_object_uid: str = "",
    node_code: str = "",
    config_path: str = "",
    priority_score: float = 0.0,
    source: str = "任务系统",
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    resource_fingerprint: str = "",
    idempotency_key: str = "",
    expected_version: str = "",
    snapshot_token: str = "",
) -> dict[str, Any]:
    """创建事务请求。"""

    request_uid = f"request-{uuid4().hex[:12]}"
    now = now_iso()
    with closing(_connect()) as connection, connection:
        schema_rows = connection.execute('PRAGMA table_info("事务请求")').fetchall()
        column_specs = [
            {
                "name": str(row[1]),
                "type": str(row[2] or ""),
                "notnull": bool(row[3]),
                "default": row[4],
            }
            for row in schema_rows
            if len(row) >= 5
        ]
        column_values: dict[str, Any] = {
            "uid_请求": request_uid,
            "uid_任务": task_uid,
            "请求类型": request_type,
            "来源对象类型": source_object_type,
            "来源对象UID": source_object_uid,
            "节点编码": node_code,
            "uid_目标事务": target_affair_uid,
            "配置路径": config_path,
            "请求状态": 请求状态_待调度,
            "优先得分": float(priority_score),
            "来源": source,
            "请求契约JSON": json.dumps(request_contract or {}, ensure_ascii=False),
            "载荷JSON": json.dumps(payload or {}, ensure_ascii=False),
            "结果JSON": "{}",
            "元数据JSON": json.dumps(metadata or {}, ensure_ascii=False),
            "调度状态": 请求状态_待调度,
            "uid_执行者": "",
            "资源指纹": resource_fingerprint,
            "幂等键": idempotency_key,
            "预期版本": expected_version,
            "快照令牌": snapshot_token,
            "租约过期时间": "",
            "提交状态": "未提交",
            "创建时间": now,
            "更新时间": now,
        }
        if "目标节点" in {item["name"] for item in column_specs}:
            column_values.setdefault("目标节点", node_code or target_affair_uid)

        for spec in column_specs:
            column_name = spec["name"]
            if column_name in column_values:
                continue
            if not spec["notnull"] or spec["default"] is not None:
                continue

            column_type = str(spec["type"] or "").upper()
            if column_name.endswith("JSON"):
                column_values[column_name] = "{}"
            elif "INT" in column_type:
                column_values[column_name] = 0
            elif any(token in column_type for token in ["REAL", "FLOA", "DOUB"]):
                column_values[column_name] = 0.0
            else:
                column_values[column_name] = ""

        ordered_columns = [spec["name"] for spec in column_specs if spec["name"] in column_values]
        placeholders = ", ".join(["?"] * len(ordered_columns))
        quoted_columns = ", ".join([f'"{name}"' for name in ordered_columns])
        connection.execute(
            f'INSERT INTO "事务请求" ({quoted_columns}) VALUES ({placeholders})',
            tuple(column_values[name] for name in ordered_columns),
        )
        row = connection.execute('SELECT * FROM "事务请求" WHERE uid_请求=?', (request_uid,)).fetchone()
        request_payload = dict(row) if row is not None else None
    if request_payload is None:
        raise KeyError(f"事务请求创建失败：{request_uid}")
    return _row_to_request(request_payload)


def get_request(request_uid: str) -> dict[str, Any]:
    """读取事务请求。"""

    with closing(_connect()) as connection, connection:
        row = connection.execute('SELECT * FROM "事务请求" WHERE uid_请求=?', (request_uid,)).fetchone()
        request_payload = dict(row) if row is not None else None
    if request_payload is None:
        raise KeyError(f"事务请求不存在：{request_uid}")
    return _row_to_request(request_payload)


def list_requests(*, status: str | None = None) -> list[dict[str, Any]]:
    """列出事务请求。"""

    with closing(_connect()) as connection, connection:
        _cleanup_expired_leases(connection, now_text=now_iso())
        if status is None:
            rows = connection.execute('SELECT * FROM "事务请求" ORDER BY "创建时间"').fetchall()
        else:
            rows = connection.execute(
                'SELECT * FROM "事务请求" WHERE "请求状态"=? ORDER BY "创建时间"',
                (status,),
            ).fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_request(row) for row in payloads]


def list_task_requests(task_uid: str) -> list[dict[str, Any]]:
    """按任务列出事务请求。"""

    with closing(_connect()) as connection, connection:
        _cleanup_expired_leases(connection, now_text=now_iso())
        rows = connection.execute(
            'SELECT * FROM "事务请求" WHERE uid_任务=? ORDER BY "创建时间"',
            (task_uid,),
        ).fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_request(row) for row in payloads]


def list_schedulable_requests(
    *,
    limit: int = 20,
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
    executor_uid: str = "",
) -> list[dict[str, Any]]:
    """列出可调度的事务请求。"""

    allowed_statuses = statuses or [请求状态_待调度, 请求状态_待租约]
    normalized_statuses = [str(item) for item in allowed_statuses if str(item).strip()]
    if not normalized_statuses:
        return []

    now_text = now_iso()
    normalized_policy = _normalize_scheduling_policy(scheduling_policy)
    preselect_limit = max(
        int(max(1, int(limit or 1)) * float(normalized_policy.get("preselect_multiplier", 4.0))),
        int(normalized_policy.get("min_preselect", 40) or 40),
    )
    with closing(_connect()) as connection, connection:
        _cleanup_expired_leases(connection, now_text=now_text)
        raw_rows = _collect_schedulable_rows(
            connection,
            statuses=normalized_statuses,
            now_text=now_text,
            fetch_limit=preselect_limit,
        )
        scored = _score_schedulable_rows(
            raw_rows,
            now_text=now_text,
            policy=normalized_policy,
            executor_uid=executor_uid,
        )
        payloads = scored[: max(1, int(limit or 1))]
    return [_row_to_request(item) for item in payloads]


def upsert_executor_heartbeat(
    *,
    executor_uid: str,
    executor_type: str = "agent",
    current_request_uid: str = "",
    status: str = 执行者状态_空闲,
    metadata: dict[str, Any] | None = None,
) -> None:
    """更新执行者心跳。"""

    now_text = now_iso()
    with closing(_connect()) as connection, connection:
        _upsert_executor_heartbeat_internal(
            connection,
            executor_uid=str(executor_uid or "").strip(),
            executor_type=str(executor_type or "agent").strip() or "agent",
            current_request_uid=str(current_request_uid or "").strip(),
            status=str(status or 执行者状态_空闲).strip() or 执行者状态_空闲,
            metadata=metadata,
            now_text=now_text,
        )


def acquire_request_lease(
    *,
    executor_uid: str,
    request_uid: str | None = None,
    lease_seconds: int = 120,
    resource_fingerprint: str = "",
    access_mode: str = "写",
    statuses: list[str] | None = None,
    scheduling_policy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """领取事务请求租约。"""

    normalized_executor_uid = str(executor_uid or "").strip()
    if not normalized_executor_uid:
        raise ValueError("executor_uid 不能为空")

    allowed_statuses = statuses or [请求状态_待调度, 请求状态_待租约]
    normalized_statuses = [str(item).strip() for item in allowed_statuses if str(item).strip()]
    if not normalized_statuses:
        normalized_statuses = [请求状态_待调度, 请求状态_待租约]

    now_text = now_iso()
    expire_text = _add_seconds_iso(now_text, lease_seconds)

    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _cleanup_expired_leases(connection, now_text=now_text)

        target_request_uid = str(request_uid or "").strip()
        if not target_request_uid:
            normalized_policy = _normalize_scheduling_policy(scheduling_policy)
            preselect_limit = max(
                int(20 * float(normalized_policy.get("preselect_multiplier", 4.0))),
                int(normalized_policy.get("min_preselect", 40) or 40),
            )
            candidate_rows = _collect_schedulable_rows(
                connection,
                statuses=normalized_statuses,
                now_text=now_text,
                fetch_limit=preselect_limit,
            )
            ranked_rows = _score_schedulable_rows(
                candidate_rows,
                now_text=now_text,
                policy=normalized_policy,
                executor_uid=normalized_executor_uid,
            )
            if not ranked_rows:
                connection.commit()
                return None
            target_request_uid = str(ranked_rows[0].get("uid_请求") or "")
            if not target_request_uid:
                connection.commit()
                return None

        request_row = _get_request_row(connection, target_request_uid)
        if request_row is None:
            connection.commit()
            return None
        request_status = str(request_row["请求状态"] or 请求状态_待调度)
        if request_status not in normalized_statuses and request_status != 请求状态_已租约:
            connection.commit()
            return None

        if request_status == 请求状态_已租约:
            active_owner = str(request_row["uid_执行者"] or "")
            active_expire = str(request_row["租约过期时间"] or "")
            if active_owner and active_owner != normalized_executor_uid and active_expire and not _is_expired(active_expire, now_text):
                connection.commit()
                return None
            if active_owner == normalized_executor_uid and active_expire and not _is_expired(active_expire, now_text):
                renewed_expire_text = _add_seconds_iso(now_text, lease_seconds)
                cursor = connection.execute(
                    'UPDATE "资源租约" SET "过期时间"=?, "心跳时间"=?, "更新时间"=? WHERE uid_请求=? AND "uid_执行者"=? AND "租约状态"=?',
                    (
                        renewed_expire_text,
                        now_text,
                        now_text,
                        target_request_uid,
                        normalized_executor_uid,
                        租约状态_已持有,
                    ),
                )
                if not cursor.rowcount:
                    connection.commit()
                    return None
                connection.execute(
                    'UPDATE "事务请求" SET "请求状态"=?, "调度状态"=?, "租约过期时间"=?, "更新时间"=? WHERE uid_请求=?',
                    (
                        请求状态_已租约,
                        请求状态_已租约,
                        renewed_expire_text,
                        now_text,
                        target_request_uid,
                    ),
                )
                refreshed_request = _get_request_row(connection, target_request_uid)
                lease_row = connection.execute(
                    'SELECT * FROM "资源租约" WHERE uid_请求=? AND "uid_执行者"=? AND "租约状态"=? ORDER BY "更新时间" DESC LIMIT 1',
                    (target_request_uid, normalized_executor_uid, 租约状态_已持有),
                ).fetchone()
                connection.commit()
                if refreshed_request is None or lease_row is None:
                    return None
                return {
                    "request": _row_to_request(dict(refreshed_request)),
                    "lease": _row_to_lease(dict(lease_row)),
                }

        resolved_fingerprint = str(resource_fingerprint or request_row["资源指纹"] or "").strip()
        if not resolved_fingerprint:
            resolved_fingerprint = f"请求:{target_request_uid}"

        lease_uid = f"lease-{uuid4().hex[:12]}"
        try:
            connection.execute(
                'INSERT INTO "资源租约" (uid_租约, uid_请求, "uid_执行者", "资源指纹", "访问模式", "租约状态", "过期时间", "心跳时间", "创建时间", "更新时间") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    lease_uid,
                    target_request_uid,
                    normalized_executor_uid,
                    resolved_fingerprint,
                    str(access_mode or "写").strip() or "写",
                    租约状态_已持有,
                    expire_text,
                    now_text,
                    now_text,
                    now_text,
                ),
            )
        except sqlite3.IntegrityError:
            connection.commit()
            return None

        connection.execute(
            'UPDATE "事务请求" SET "请求状态"=?, "调度状态"=?, "uid_执行者"=?, "资源指纹"=?, "租约过期时间"=?, "更新时间"=? WHERE uid_请求=?',
            (
                请求状态_已租约,
                请求状态_已租约,
                normalized_executor_uid,
                resolved_fingerprint,
                expire_text,
                now_text,
                target_request_uid,
            ),
        )
        _upsert_executor_heartbeat_internal(
            connection,
            executor_uid=normalized_executor_uid,
            executor_type="agent",
            current_request_uid=target_request_uid,
            status=执行者状态_忙碌,
            metadata={"lease_uid": lease_uid},
            now_text=now_text,
        )

        request_payload = _get_request_row(connection, target_request_uid)
        lease_row = connection.execute('SELECT * FROM "资源租约" WHERE uid_租约=?', (lease_uid,)).fetchone()
        connection.commit()

    if request_payload is None or lease_row is None:
        return None
    return {
        "request": _row_to_request(dict(request_payload)),
        "lease": _row_to_lease(dict(lease_row)),
    }


def renew_request_lease(
    *,
    request_uid: str,
    executor_uid: str,
    lease_seconds: int = 120,
) -> bool:
    """续租事务请求。"""

    now_text = now_iso()
    expire_text = _add_seconds_iso(now_text, lease_seconds)
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _cleanup_expired_leases(connection, now_text=now_text)
        cursor = connection.execute(
            'UPDATE "资源租约" SET "过期时间"=?, "心跳时间"=?, "更新时间"=? WHERE uid_请求=? AND "uid_执行者"=? AND "租约状态"=?',
            (expire_text, now_text, now_text, request_uid, executor_uid, 租约状态_已持有),
        )
        if not cursor.rowcount:
            connection.commit()
            return False
        connection.execute(
            'UPDATE "事务请求" SET "租约过期时间"=?, "更新时间"=? WHERE uid_请求=? AND "uid_执行者"=?',
            (expire_text, now_text, request_uid, executor_uid),
        )
        _upsert_executor_heartbeat_internal(
            connection,
            executor_uid=executor_uid,
            executor_type="agent",
            current_request_uid=request_uid,
            status=执行者状态_忙碌,
            metadata={"renew": True},
            now_text=now_text,
        )
        connection.commit()
    return True


def release_request_lease(
    *,
    request_uid: str,
    executor_uid: str,
    lease_status: str = 租约状态_已释放,
    heartbeat_status: str = 执行者状态_空闲,
) -> bool:
    """释放事务请求租约。"""

    now_text = now_iso()
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _cleanup_expired_leases(connection, now_text=now_text)
        cursor = connection.execute(
            'UPDATE "资源租约" SET "租约状态"=?, "更新时间"=? WHERE uid_请求=? AND "uid_执行者"=? AND "租约状态"=?',
            (
                str(lease_status or 租约状态_已释放),
                now_text,
                request_uid,
                executor_uid,
                租约状态_已持有,
            ),
        )
        connection.execute(
            'UPDATE "事务请求" SET "uid_执行者"=?, "租约过期时间"=?, "更新时间"=? WHERE uid_请求=? AND "uid_执行者"=?',
            ("", "", now_text, request_uid, executor_uid),
        )
        _upsert_executor_heartbeat_internal(
            connection,
            executor_uid=executor_uid,
            executor_type="agent",
            current_request_uid="",
            status=str(heartbeat_status or 执行者状态_空闲),
            metadata={"release_request_uid": request_uid},
            now_text=now_text,
        )
        connection.commit()
    return bool(cursor.rowcount)


def update_request_status(
    request_uid: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    merge_metadata: bool = True,
) -> None:
    """更新事务请求状态。"""

    current = get_request(request_uid)
    normalized_status = _resolve_schedule_status(status)
    next_metadata = dict(metadata or {})
    if merge_metadata:
        merged = dict(current.get("metadata") or {})
        merged.update(next_metadata)
        next_metadata = merged

    commit_status = str(current.get("commit_status") or "未提交")
    if normalized_status in {请求状态_待提交, 请求状态_已提交, 请求状态_已完成}:
        commit_status = "已提交"

    request_executor_uid = str(current.get("executor_uid") or "")
    if normalized_status in {请求状态_待调度, 请求状态_待租约, 请求状态_已完成, 请求状态_已阻断, 请求状态_已失败, 请求状态_已取消}:
        request_executor_uid = ""

    lease_expire_at = str(current.get("lease_expire_at") or "")
    if normalized_status in {请求状态_待调度, 请求状态_待租约, 请求状态_已完成, 请求状态_已阻断, 请求状态_已失败, 请求状态_已取消}:
        lease_expire_at = ""

    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            'UPDATE "事务请求" SET "请求状态"=?, "调度状态"=?, "uid_执行者"=?, "租约过期时间"=?, "提交状态"=?, "结果JSON"=?, "元数据JSON"=?, "更新时间"=? WHERE uid_请求=?',
            (
                normalized_status,
                normalized_status,
                request_executor_uid,
                lease_expire_at,
                commit_status,
                json.dumps(result or current.get("result") or {}, ensure_ascii=False),
                json.dumps(next_metadata, ensure_ascii=False),
                now_iso(),
                request_uid,
            ),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"事务请求不存在：{request_uid}")


def mark_request_running(request_uid: str) -> None:
    """标记事务请求为执行中。"""

    update_request_status(request_uid, status=请求状态_执行中)


def mark_request_ready_for_commit(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为待提交。"""

    update_request_status(request_uid, status=请求状态_待提交, result=result)


def mark_request_committed(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已提交。"""

    update_request_status(request_uid, status=请求状态_已提交, result=result)


def mark_request_completed(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已完成。"""

    update_request_status(request_uid, status=请求状态_已完成, result=result)


def mark_request_blocked(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已阻断。"""

    update_request_status(request_uid, status=请求状态_已阻断, result=result)


def mark_request_failed(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已失败。"""

    update_request_status(request_uid, status=请求状态_已失败, result=result)


def mark_request_cancelled(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已取消。"""

    update_request_status(request_uid, status=请求状态_已取消, result=result)