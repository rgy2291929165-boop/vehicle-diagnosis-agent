"""客户端负责启动、连接和关闭本地 DTC MCP 子进程。"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def connect_dtc_server():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.dtc_mcp_server"],
        cwd=PROJECT_ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    async with Client(parameters, read_timeout_seconds=10.0) as client:
        yield client
