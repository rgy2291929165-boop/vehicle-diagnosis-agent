"""将 stdio MCP 查询适配为诊断图已有的同步只读工具接口。"""

import asyncio

from anyio import BrokenResourceError, ClosedResourceError, EndOfStream
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT, TextContent
from pydantic import ValidationError

from app.dtc_mcp_client import connect_dtc_server
from app.dtc_mcp_contract import DtcQuery, DtcResult
from app.tool_router import ToolExecutionFailed


def _leaves(group: BaseExceptionGroup) -> list[BaseException]:
    errors = []
    for error in group.exceptions:
        if isinstance(error, BaseExceptionGroup):
            errors.extend(_leaves(error))
        else:
            errors.append(error)
    return errors


async def lookup_dtc_via_mcp_async(vehicle_id: str, dtc_code: str) -> dict:
    query = DtcQuery(vehicle_id=vehicle_id, dtc_code=dtc_code)
    try:
        async with connect_dtc_server() as client:
            result = await client.call_tool("lookup_dtc", query.model_dump())
    except* MCPError as failures:
        errors = _leaves(failures)
        message = "; ".join(str(error) for error in errors)
        if all(error.code == REQUEST_TIMEOUT for error in errors):
            raise TimeoutError(f"MCP 查询超时：{message}") from failures
        if all(error.code == CONNECTION_CLOSED for error in errors):
            raise ConnectionError(f"MCP 连接关闭：{message}") from failures
        raise ToolExecutionFailed("tool_remote_error", f"MCP 协议错误：{message}") from failures
    except* TimeoutError as failures:
        raise TimeoutError("MCP 查询超时") from failures
    except* (OSError, EOFError, EndOfStream, BrokenResourceError, ClosedResourceError) as failures:
        raise ConnectionError("MCP 服务不可用或连接中断") from failures

    if result.is_error:
        message = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        if (result.meta or {}).get("failure_reason") == "tool_data_not_found":
            raise LookupError(message or "MCP DTC 查无记录")
        raise ToolExecutionFailed("tool_remote_error", f"MCP 工具返回错误：{message}")

    try:
        payload = DtcResult.model_validate(result.structured_content)
    except ValidationError as error:
        raise ToolExecutionFailed("invalid_tool_result", "MCP DTC 返回数据不符合协议") from error
    if payload.vehicle_id != query.vehicle_id or payload.dtc_code != query.dtc_code.upper():
        raise ToolExecutionFailed("invalid_tool_result", "MCP DTC 返回的车辆或故障码与请求不一致")
    return payload.model_dump()


def lookup_dtc_via_mcp(vehicle_id: str, dtc_code: str) -> dict:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(lookup_dtc_via_mcp_async(vehicle_id, dtc_code))
    raise RuntimeError("异步调用环境请使用诊断图 ainvoke，或直接 await lookup_dtc_via_mcp_async")
