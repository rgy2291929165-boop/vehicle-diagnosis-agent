"""第三周 Day 2：诊断状态与信息完整性检查。"""

from __future__ import annotations

from typing import Literal, TypedDict


class DiagnosisState(TypedDict):
    """进入工具路由前需要收集的最小诊断信息。"""

    vehicle_id: str | None
    symptom: str | None
    dtc_codes: list[str]
    missing_fields: list[str]
    next_action: Literal["ask_clarifying_question", "route_tools"]
    clarifying_question: str | None
    trace: list[str]


class CompletenessUpdate(TypedDict):
    """完整性检查节点返回的状态更新。"""

    missing_fields: list[str]
    next_action: Literal["ask_clarifying_question", "route_tools"]
    clarifying_question: str | None
    trace: list[str]


FIELD_LABELS = {
    "vehicle_id": "车辆标识（vehicle_id）",
    "symptom": "故障现象（symptom）",
    "dtc_codes": "故障码（DTC）",
}


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_dtc_code(dtc_codes: list[str]) -> bool:
    return any(isinstance(code, str) and code.strip() for code in dtc_codes)


def check_information_completeness(state: DiagnosisState) -> CompletenessUpdate:
    """检查工具查询所需字段，并返回补问或工具路由决策。

    此函数只创建并返回状态更新，不会原地修改调用者传入的 ``state``。
    """

    missing_fields = []
    if not _has_text(state["vehicle_id"]):
        missing_fields.append("vehicle_id")
    if not _has_text(state["symptom"]):
        missing_fields.append("symptom")
    if not _has_dtc_code(state["dtc_codes"]):
        missing_fields.append("dtc_codes")

    trace = [*state["trace"], "check_information_completeness"]
    if missing_fields:
        labels = "、".join(FIELD_LABELS[field] for field in missing_fields)
        return {
            "missing_fields": missing_fields,
            "next_action": "ask_clarifying_question",
            "clarifying_question": f"请补充以下诊断信息：{labels}。",
            "trace": trace,
        }

    return {
        "missing_fields": [],
        "next_action": "route_tools",
        "clarifying_question": None,
        "trace": trace,
    }
