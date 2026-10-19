"""工具执行前的预算检查与重复调用检测。"""

import json

from app.tool_router import execute_tool_call

class ToolCallRejected(RuntimeError):
    """工具调用因预算或重复检测被拒绝。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason

def _call_signature(call: dict) -> str:
    """将工具名和参数转换为稳定的字符串，忽略字典键顺序。"""

    return json.dumps(
        {
            "tool_name": call.get("tool_name"),
            "arguments": call.get("arguments"),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def execute_guarded_tool_call(call: dict, run_state: dict, *, dtc_lookup=None) -> dict:
    count = run_state["tool_call_count"]
    limit = run_state["max_tool_calls"]
    trace = run_state["tool_trace"]
    tool_name = call.get("tool_name", "<invalid>")

    if type(count) is not int or count < 0:
        raise ValueError("tool_call_count 必须是非负整数")
    if type(limit) is not int or limit < 1:
        raise ValueError("max_tool_calls 必须是正整数")

    if count >= limit:
        trace.append(
            {
                "tool_name": tool_name,
                "status": "rejected",
                "reason": "tool_call_limit",
            }
        )
        raise ToolCallRejected(
            "tool_call_limit",
            f"工具调用次数已达到上限：{limit}",
      )

    signature = _call_signature(call)
    seen_calls = run_state["seen_tool_calls"]

    if signature in seen_calls:
        trace.append(
            {
                "tool_name": tool_name,
                "status": "rejected",
                "reason": "duplicate_tool_call",
            }
        )

        raise ToolCallRejected(
           "duplicate_tool_call",
           f"拒绝重复调用工具：{tool_name}",
    )

    # 获准调用才消耗预算并保存签名，报错也不退还。
    run_state["tool_call_count"] = count + 1
    seen_calls.append(signature)

    return execute_tool_call(call, trace, dtc_lookup=dtc_lookup)
