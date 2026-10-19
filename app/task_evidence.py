"""按白名单读取本地已审核摘要；无模型、网络或工单写入。"""

import json
from pathlib import Path

from app.task_contracts import EvidenceItem, EvidencePack


SOURCE_INVENTORY_PATH = (
    Path(__file__).resolve().parent.parent / "evaluation/week5/source_inventory.json"
)
TOPIC_SOURCE_IDS = {
    "charge_port_RED": "w5-red",
    "CP_a054": "w5-cp_a054",
}


def _require_text_list(value, name: str, *, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{name} 必须是{'可空' if allow_empty else '非空'}的非空字符串列表")
    return [item.strip() for item in value]


def lookup_charge_reference(topic: str, *, task_id: str) -> EvidencePack:
    """查询所选资料，服务端提供任务 ID；不确认具体车辆适用性或故障。"""
    if not isinstance(topic, str) or topic not in TOPIC_SOURCE_IDS:
        raise ValueError("不支持的资料主题，只允许 charge_port_RED 或 CP_a054")
    task = EvidencePack(task_id=task_id)

    try:
        inventory = json.loads(SOURCE_INVENTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("无法读取资料清单") from error
    sources = inventory.get("sources") if isinstance(inventory, dict) else None
    if not isinstance(sources, list) or any(not isinstance(row, dict) for row in sources):
        raise ValueError("资料清单的 sources 必须是记录列表")

    source_id = TOPIC_SOURCE_IDS[topic]
    matches = [row for row in sources if row.get("source_id") == source_id]
    if len(matches) != 1:
        raise ValueError("目标来源必须存在且只能有一条记录")
    source = matches[0]
    if source.get("material_kind") != "official_source_chinese_summary_with_coach_review":
        raise ValueError("目标来源不是当前已审核摘要")

    claims = _require_text_list(source.get("verified_claims"), "verified_claims")
    unknown_scope = _require_text_list(
        source.get("unknown_scope"), "unknown_scope", allow_empty=True,
    )
    item = EvidenceItem(
        chunk_id=f"{source_id}:reviewed:0",
        document_id=source.get("local_document_id"),
        source=source.get("official_url"),
        text="\n".join(claims),
        material_kind="reviewed_summary",
        limitations=[
            "经人工复核的中文摘要，非完整原文",
            "个性化车辆适用性未核实",
            *[f"资料适用性未知：{field}" for field in unknown_scope],
        ],
    )
    return EvidencePack(task_id=task.task_id, items=[item])
