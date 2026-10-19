"""第三周 Day 5：从诊断状态构造受限的结构化工具调用。"""

from __future__ import annotations

from typing import TypedDict

from app.tool_router import ALLOWED_TOOLS


class ToolCall(TypedDict):
    tool_name: str
    arguments: dict[str, str]


def _require_text(state: dict, field_name: str) -> str:
    value = state.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空")
    return value.strip()


def _first_dtc_code(state: dict) -> str:
    dtc_codes = state.get("dtc_codes")
    if not isinstance(dtc_codes, list) or not dtc_codes:
        raise ValueError("dtc_codes 不能为空")

    first_code = dtc_codes[0]
    if not isinstance(first_code, str) or not first_code.strip():
        raise ValueError("dtc_codes 不能为空")

    return first_code.strip().upper()


def build_tool_call(requested_tool: str, state: dict) -> ToolCall:
    """将状态字段映射为允许列表中的一种工具调用。"""

    if requested_tool not in ALLOWED_TOOLS:
        raise PermissionError(f"不允许规划工具：{requested_tool}")

    if requested_tool == "lookup_dtc":
        return {
            "tool_name": "lookup_dtc",
            "arguments": {
                "vehicle_id": _require_text(state, "vehicle_id"),
                "dtc_code": _first_dtc_code(state),
            },
        }

    if requested_tool == "lookup_vehicle_history":
        return {
            "tool_name": "lookup_vehicle_history",
            "arguments": {
                "vehicle_id": _require_text(state, "vehicle_id"),
            },
        }

    return {
        "tool_name": "lookup_inventory",
        "arguments": {
            "part_number": _require_text(state, "part_number").upper(),
        },
    }