"""启动独立 MCP 服务，通过 stdio 发现工具并查询模拟 DTC。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.types import TextContent

from app.dtc_mcp_client import connect_dtc_server


async def run_demo(vehicle_id: str, dtc_code: str) -> int:
    async with connect_dtc_server() as client:
        tools = (await client.list_tools()).tools
        print("服务名称：", client.server_info.name)
        print("传输方式：stdio，客户端自动启动独立服务进程")
        print("发现工具：", [tool.name for tool in tools])
        for tool in tools:
            print("只读标记：", tool.annotations.read_only_hint)
            print("输入协议：", json.dumps(tool.input_schema, ensure_ascii=False))

        result = await client.call_tool("lookup_dtc", {
            "vehicle_id": vehicle_id, "dtc_code": dtc_code,
        })
        print("工具调用失败：", result.is_error)
        if result.is_error:
            for block in result.content:
                if isinstance(block, TextContent):
                    print("错误：", block.text)
            return 1

        print("查询结果：", json.dumps(result.structured_content, ensure_ascii=False, indent=2))
        print("数据说明：固定模拟目录，仅用于验证 MCP 调用，不代表实车维修结论。")
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle-id", default="VIN-DEMO-001")
    parser.add_argument("--dtc", default="P0AA6")
    args = parser.parse_args()
    return asyncio.run(run_demo(args.vehicle_id, args.dtc))


if __name__ == "__main__":
    raise SystemExit(main())
