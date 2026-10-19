import asyncio
from copy import deepcopy

from mcp import Client
from mcp.types import TextContent
import pytest

from app import diagnostic_tools
from app.dtc_mcp_client import connect_dtc_server
from app.dtc_mcp_server import build_dtc_mcp_server


def error_text(result):
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


def test_server_exposes_only_the_readonly_dtc_tool_and_its_input_schema():
    async def scenario():
        async with Client(build_dtc_mcp_server()) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == ["lookup_dtc"]
            tool = tools[0]
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.open_world_hint is False
            assert set(tool.input_schema["required"]) == {"vehicle_id", "dtc_code"}
            assert set(tool.input_schema["properties"]) == {"vehicle_id", "dtc_code"}
            assert tool.input_schema["properties"]["vehicle_id"]["type"] == "string"
            assert tool.input_schema["properties"]["dtc_code"]["type"] == "string"
            assert tool.output_schema is not None
    asyncio.run(scenario())


def test_lookup_returns_structured_mock_data_and_does_not_change_the_catalog():
    before = deepcopy(diagnostic_tools.DTC_CATALOG)
    async def scenario():
        async with Client(build_dtc_mcp_server()) as client:
            result = await client.call_tool("lookup_dtc", {
                "vehicle_id": " VIN-DEMO-001 ", "dtc_code": " p0aa6 ",
            })
            assert not result.is_error
            assert result.structured_content == {
                **diagnostic_tools.lookup_dtc("VIN-DEMO-001", "P0AA6"),
                "data_source": "mock",
            }
    asyncio.run(scenario())
    assert diagnostic_tools.DTC_CATALOG == before


@pytest.mark.parametrize("arguments", [
    {"dtc_code": "P0AA6"},
    {"vehicle_id": "VIN-DEMO-001"},
    {"vehicle_id": "   ", "dtc_code": "P0AA6"},
    {"vehicle_id": "VIN-DEMO-001", "dtc_code": "   "},
    {"vehicle_id": "VIN-DEMO-001", "dtc_code": 123},
    {"vehicle_id": None, "dtc_code": "P0AA6"},
])
def test_invalid_arguments_return_a_tool_error_and_do_not_break_the_session(arguments):
    async def scenario():
        async with Client(build_dtc_mcp_server()) as client:
            invalid = await client.call_tool("lookup_dtc", arguments)
            assert invalid.is_error
            assert invalid.structured_content is None
            assert error_text(invalid)
            valid = await client.call_tool("lookup_dtc", {
                "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0AA6",
            })
            assert not valid.is_error
    asyncio.run(scenario())


def test_unknown_dtc_has_an_explicit_tool_error_instead_of_a_success_payload():
    async def scenario():
        async with Client(build_dtc_mcp_server()) as client:
            result = await client.call_tool("lookup_dtc", {
                "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0123",
            })
            assert result.is_error
            assert result.structured_content is None
            assert "DTC 未找到：P0123" in error_text(result)
    asyncio.run(scenario())


@pytest.mark.parametrize("name", ["create_work_order", "delete_work_order"])
def test_unregistered_write_tools_cannot_be_called(name):
    async def scenario():
        async with Client(build_dtc_mcp_server()) as client:
            result = await client.call_tool(name, {})
            assert result.is_error
            assert result.structured_content is None
    asyncio.run(scenario())


def test_stdio_connects_to_a_separate_server_process_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(diagnostic_tools.DTC_CATALOG["P0AA6"], "description", "父进程中临时修改")
    async def scenario():
        async with connect_dtc_server() as client:
            assert client.server_info.name == "vehicle-dtc-readonly"
            assert [tool.name for tool in (await client.list_tools()).tools] == ["lookup_dtc"]
            result = await client.call_tool("lookup_dtc", {
                "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0AA6",
            })
            assert not result.is_error
            assert result.structured_content["description"] == "高压系统绝缘电阻低"
            assert result.structured_content["data_source"] == "mock"
    asyncio.run(scenario())
    assert list(tmp_path.iterdir()) == []


def test_stdio_session_handles_an_error_followed_by_a_success():
    async def scenario():
        async with connect_dtc_server() as client:
            missing = await client.call_tool("lookup_dtc", {
                "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0123",
            })
            assert missing.is_error
            assert "DTC 未找到：P0123" in error_text(missing)
            found = await client.call_tool("lookup_dtc", {
                "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0AA6",
            })
            assert not found.is_error
            assert found.structured_content["dtc_code"] == "P0AA6"
    asyncio.run(scenario())
