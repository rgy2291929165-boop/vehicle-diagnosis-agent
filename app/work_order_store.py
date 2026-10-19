"""将已批准且内容一致的草稿幂等地保存到本地 SQLite 工单库。"""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


def create_work_order_once(
    state: dict, *, idempotency_key: str, database_path: str | Path,
) -> dict:
    """state 来自审批图的 checkpoint；相同键和内容返回同一条工单。"""
    if not isinstance(state, dict) or state.get("status") != "approved":
        raise ValueError("只有已批准的草稿可以提交工单")

    draft = state.get("draft")
    if not isinstance(draft, dict) or draft.get("status") != "approved":
        raise ValueError("草稿状态必须为 approved")

    history = state.get("review_history")
    approval = history[-1] if isinstance(history, list) and history else None
    if (
        not isinstance(approval, dict)
        or approval.get("decision") != {"action": "approve"}
        or approval.get("status") != "approved"
        or approval.get("error") is not None
        or state.get("review_error") is not None
        or approval.get("draft") != draft
    ):
        raise ValueError("当前草稿与最后一次有效批准记录不一致")

    for name in ("vehicle_id", "symptom", "title", "description"):
        value = draft.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} 必须是非空字符串")
    codes = draft.get("dtc_codes")
    if (
        not isinstance(codes, list) or not codes
        or any(not isinstance(code, str) or not code.strip() for code in codes)
    ):
        raise ValueError("dtc_codes 必须是非空的故障码字符串列表")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key 必须是非空字符串")

    # 保留已批准内容的原样快照；排序仅消除字典键顺序对比较的影响。
    payload = json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = idempotency_key.strip()
    database = Path(database_path).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS work_orders (
                    work_order_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    approved_draft_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                INSERT INTO work_orders
                    (work_order_id, idempotency_key, status, approved_draft_json)
                VALUES (?, ?, 'open', ?)
                ON CONFLICT(idempotency_key) DO NOTHING
            """, (str(uuid4()), key, payload))
            row = connection.execute("""
                SELECT work_order_id, status, approved_draft_json
                FROM work_orders WHERE idempotency_key = ?
            """, (key,)).fetchone()
            if row[2] != payload:
                raise ValueError("幂等键对应的工单内容不一致，已有工单未被覆盖")

    return {
        "work_order_id": row[0],
        "idempotency_key": key,
        "status": row[1],
        "draft": json.loads(row[2]),
    }
