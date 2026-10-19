"""第三周 Day 4：只读工具的允许列表、参数校验与轨迹记录。"""

from collections.abc import Callable

from app.diagnostic_tools import (
    lookup_dtc,
    lookup_inventory,
    lookup_vehicle_history,
)

ALLOWED_TOOLS = {
    "lookup_dtc",
    "lookup_vehicle_history",
    "lookup_inventory",
}

TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "lookup_dtc": lookup_dtc,
    "lookup_vehicle_history": lookup_vehicle_history,
    "lookup_inventory": lookup_inventory,
}

TOOL_SCHEMAS = {
    "lookup_dtc": {"vehicle_id", "dtc_code"},
    "lookup_vehicle_history": {"vehicle_id"},
    "lookup_inventory": {"part_number"},
}


class ToolExecutionFailed(RuntimeError):
    """工具报告的预期运行故障，可在诊断图中转为人工复核请求。"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _reject(trace: list[dict], tool_name: str, reason: str) -> None:
    trace.append(
        {
            "tool_name": tool_name,
            "status": "rejected",
            "reason": reason,
        }
    )


def _validate_arguments(tool_name: str, arguments: object) -> dict:
    if not isinstance(arguments, dict):
        raise ValueError("arguments 必须是对象")

    expected_fields = TOOL_SCHEMAS[tool_name]
    if set(arguments) != expected_fields:
        raise ValueError(f"{tool_name} 的参数字段不匹配")

    if not all(
        isinstance(value, str) and value.strip()
        for value in arguments.values()
    ):
        raise ValueError(f"{tool_name} 的参数不能为空")

    return arguments


def execute_tool_call(call: dict, trace: list[dict], *, dtc_lookup: Callable[..., dict] | None = None) -> dict:
    """校验工具名和参数后执行只读工具，并记录结果。"""

    tool_name = call.get("tool_name")
    if not isinstance(tool_name, str) or tool_name not in ALLOWED_TOOLS:
        rejected_name = tool_name if isinstance(tool_name, str) else "<invalid>"
        _reject(trace, rejected_name, "tool_not_allowed")
        raise PermissionError(f"不允许调用工具：{rejected_name}")

    try:
        arguments = _validate_arguments(tool_name, call.get("arguments"))
    except ValueError:
        _reject(trace, tool_name, "invalid_arguments")
        raise

    try:
        tool = dtc_lookup if tool_name == "lookup_dtc" and dtc_lookup is not None else TOOL_REGISTRY[tool_name]
        result = tool(**arguments)
    except ToolExecutionFailed as error:
        trace.append({
            "tool_name": tool_name,
            "status": "error",
            "reason": error.reason,
            "error_type": type(error).__name__,
            "message": str(error),
        })
        raise
    except (TimeoutError, ConnectionError, LookupError) as error:
        # 模拟目录用精确的 LookupError 表示查无记录。
        # KeyError/IndexError 等属于程序缺陷，不能冒充业务查无记录。
        if isinstance(error, LookupError) and type(error) is not LookupError:
            raise
        if isinstance(error, TimeoutError):
            reason, message = "tool_timeout", "调用超时"
        elif isinstance(error, ConnectionError):
            reason, message = "tool_unavailable", "连接失败"
        else:
            reason, message = "tool_data_not_found", "查无记录"
        trace.append({
            "tool_name": tool_name,
            "status": "error",
            "reason": reason,
            "error_type": type(error).__name__,
            "message": str(error),
        })
        raise ToolExecutionFailed(reason, f"工具 {tool_name} {message}") from error
    trace.append(
        {
            "tool_name": tool_name,
            "status": "success",
        }
    )
    return result
