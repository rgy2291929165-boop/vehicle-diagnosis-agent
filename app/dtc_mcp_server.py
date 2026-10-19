"""只暴露一个只读工具的 stdio MCP 服务，数据来自固定模拟目录。"""

import json
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from app.diagnostic_tools import lookup_dtc as lookup_mock_dtc
from app.dtc_mcp_contract import DtcResult, NonEmptyText


def build_dtc_mcp_server() -> MCPServer:
    server = MCPServer(
        "vehicle-dtc-readonly",
        instructions="只读教学 DTC 查询；返回模拟数据，不代表真实车辆诊断或维修结论。",
        log_level="WARNING",
    )

    @server.tool(
        name="lookup_dtc",
        title="只读模拟 DTC 查询",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def lookup_dtc(vehicle_id: NonEmptyText, dtc_code: NonEmptyText) -> Annotated[CallToolResult, DtcResult]:
        """按车辆标识和故障码查询固定模拟目录；不写入工单或车辆数据。"""
        try:
            record = lookup_mock_dtc(vehicle_id, dtc_code)
        except LookupError as error:
            if type(error) is not LookupError:
                raise
            return CallToolResult(
                content=[TextContent(type="text", text=str(error))],
                is_error=True,
                meta={"failure_reason": "tool_data_not_found"},
            )
        payload = {**record, "data_source": "mock"}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structured_content=payload,
        )

    return server


if __name__ == "__main__":
    build_dtc_mcp_server().run(transport="stdio")
