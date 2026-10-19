import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import sys

from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, CONNECTION_CLOSED, REQUEST_TIMEOUT, TextContent
from langgraph.checkpoint.sqlite import SqliteSaver
import pytest

from app import dtc_mcp_adapter as adapter, tool_router
from app.diagnosis_graph import build_diagnosis_graph
from app.diagnostic_tools import lookup_dtc
from scripts.run_diagnosis_demo import make_state


def payload():
    return {**lookup_dtc("VIN-DEMO-001", "P0AA6"), "data_source": "mock"}


def fake_connection(monkeypatch, *, result=None, error=None):
    calls = []
    class FakeClient:
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            return result
    @asynccontextmanager
    async def connect():
        if error is not None:
            raise error
        yield FakeClient()
    monkeypatch.setattr(adapter, "connect_dtc_server", connect)
    return calls


def mcp_graph(checkpointer=None):
    return build_diagnosis_graph(checkpointer, dtc_lookup=adapter.lookup_dtc_via_mcp)


def test_graph_uses_real_stdio_without_replacing_the_default_registry(monkeypatch):
    original_lookup = tool_router.TOOL_REGISTRY["lookup_dtc"]
    def local_only(**arguments):
        return {**original_lookup(**arguments), "description": "本地替代实现"}
    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", local_only)
    before_registry = dict(tool_router.TOOL_REGISTRY)
    result = mcp_graph().invoke(make_state([]))
    assert result["status"] == "no_evidence"
    assert result["tool_call_count"] == 1
    assert result["tool_result"] == payload()
    assert result["tool_trace"] == [{"tool_name": "lookup_dtc", "status": "success"}]
    assert result["trace"][-2:] == ["retrieve_knowledge", "format_diagnosis"]
    assert tool_router.TOOL_REGISTRY == before_registry
    local = build_diagnosis_graph().invoke(make_state([]))
    assert local["tool_result"]["description"] == "本地替代实现"


def test_mcp_result_continues_to_retrieval_and_source_display():
    chunk = {
        "chunk_id": "mcp-flow:0", "document_id": "mcp-flow",
        "text": "P0AA6 教学片段，仅验证 MCP 与引用流程。", "source": "demo/mcp-flow",
    }
    result = mcp_graph().invoke(make_state([chunk]))
    assert result["status"] == "ok"
    assert result["tool_result"]["data_source"] == "mock"
    assert result["citations"] == [{key: chunk[key] for key in ("chunk_id", "document_id", "source")}]
    assert chunk["text"] in result["answer"]


@pytest.mark.parametrize("overrides, status, reason", [
    ({"dtc_codes": []}, "needs_info", None),
    ({"tool_call_count": 2}, "stopped", "tool_call_limit"),
    ({"seen_tool_calls": [json.dumps({
        "tool_name": "lookup_dtc", "arguments": {"vehicle_id": "VIN-DEMO-001", "dtc_code": "P0AA6"},
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))]}, "stopped", "duplicate_tool_call"),
])
def test_info_and_guard_checks_happen_before_any_mcp_connection(monkeypatch, overrides, status, reason):
    @asynccontextmanager
    async def forbidden():
        pytest.fail("此路径不应启动 MCP 连接")
        yield
    monkeypatch.setattr(adapter, "connect_dtc_server", forbidden)
    result = mcp_graph().invoke(make_state([], **overrides))
    assert result["status"] == status
    assert result["stop_reason"] == reason


@pytest.mark.parametrize("change", [
    {"vehicle_id": "VIN-OTHER"}, {"dtc_code": "P0123"},
    {"data_source": "real"}, {"description": None},
])
def test_invalid_or_mismatched_remote_results_are_not_used_as_evidence(monkeypatch, change):
    result = CallToolResult(content=[], structured_content={**payload(), **change})
    fake_connection(monkeypatch, result=result)
    output = mcp_graph().invoke(make_state([]))
    assert output["status"] == "needs_human"
    assert output["stop_reason"] == "invalid_tool_result"
    assert output["tool_result"] is None
    assert output["citations"] == []
    assert output["tool_trace"][-1]["reason"] == "invalid_tool_result"
    assert "retrieve_knowledge" not in output["trace"]


def test_remote_missing_record_is_classified_by_metadata_instead_of_message_text(monkeypatch):
    remote = CallToolResult(
        content=[TextContent(type="text", text="No matching record in this catalog")],
        is_error=True, meta={"failure_reason": "tool_data_not_found"},
    )
    fake_connection(monkeypatch, result=remote)
    result = mcp_graph().invoke(make_state([]))
    assert result["status"] == "needs_human"
    assert result["stop_reason"] == "tool_data_not_found"
    assert result["tool_call_count"] == 1


def test_remote_error_without_a_known_reason_is_not_reported_as_not_found(monkeypatch):
    fake_connection(monkeypatch, result=CallToolResult(
        content=[TextContent(type="text", text="Remote execution failed")], is_error=True,
    ))
    result = mcp_graph().invoke(make_state([]))
    assert result["status"] == "needs_human"
    assert result["stop_reason"] == "tool_remote_error"


@pytest.mark.parametrize("error, reason", [
    (MCPError(REQUEST_TIMEOUT, "read timed out"), "tool_timeout"),
    (MCPError(CONNECTION_CLOSED, "closed"), "tool_unavailable"),
    (FileNotFoundError("server executable missing"), "tool_unavailable"),
    (ExceptionGroup("transport", [MCPError(CONNECTION_CLOSED, "closed")]), "tool_unavailable"),
])
def test_known_transport_errors_keep_budget_and_prepare_review(monkeypatch, error, reason):
    fake_connection(monkeypatch, error=error)
    result = mcp_graph().invoke(make_state([]))
    assert result["status"] == "needs_human"
    assert result["stop_reason"] == reason
    assert result["tool_call_count"] == 1
    assert len(result["seen_tool_calls"]) == 1
    assert result["handoff_request"]["reason"] == reason


@pytest.mark.parametrize("program, timeout, reason", [
    ("pass", 1.0, "tool_unavailable"),
    ("import time; time.sleep(1)", 0.03, "tool_timeout"),
])
def test_real_unresponsive_or_exited_subprocess_is_classified(monkeypatch, program, timeout, reason):
    @asynccontextmanager
    async def broken_server():
        parameters = StdioServerParameters(command=sys.executable, args=["-c", program])
        async with Client(parameters, mode="legacy", read_timeout_seconds=timeout) as client:
            yield client
    monkeypatch.setattr(adapter, "connect_dtc_server", broken_server)
    result = mcp_graph().invoke(make_state([]))
    assert result["status"] == "needs_human"
    assert result["stop_reason"] == reason
    assert result["tool_call_count"] == 1


def test_mixed_unexpected_program_error_is_not_silently_converted(monkeypatch):
    fake_connection(monkeypatch, error=ExceptionGroup("mixed", [
        MCPError(CONNECTION_CLOSED, "closed"), RuntimeError("代码缺陷"),
    ]))
    with pytest.raises(ExceptionGroup) as raised:
        adapter.lookup_dtc_via_mcp("VIN-DEMO-001", "P0AA6")
    assert raised.value.subgroup(RuntimeError) is not None


def test_sync_bridge_reports_incorrect_event_loop_usage():
    async def scenario():
        with pytest.raises(RuntimeError, match="ainvoke"):
            adapter.lookup_dtc_via_mcp("VIN-DEMO-001", "P0AA6")
    asyncio.run(scenario())


def test_graph_ainvoke_works_with_the_sync_mcp_adapter():
    async def scenario():
        result = await mcp_graph().ainvoke(make_state([]))
        assert result["tool_result"] == payload()
        assert result["status"] == "no_evidence"
    asyncio.run(scenario())


def test_checkpoint_reopen_keeps_mcp_guard_state_and_blocks_repeated_query(tmp_path, monkeypatch):
    database = str(tmp_path / "diagnosis.sqlite")
    config = {"configurable": {"thread_id": "mcp-flow"}}
    with SqliteSaver.from_conn_string(database) as saver:
        first = mcp_graph(saver).invoke(make_state([]), config)
    before = deepcopy(first)
    @asynccontextmanager
    async def forbidden():
        pytest.fail("重复调用不应启动 MCP")
        yield
    monkeypatch.setattr(adapter, "connect_dtc_server", forbidden)
    with SqliteSaver.from_conn_string(database) as saver:
        result = mcp_graph(saver).invoke({"requested_tool": "lookup_dtc"}, config)
        assert result["status"] == "stopped"
        assert result["stop_reason"] == "duplicate_tool_call"
        assert result["tool_call_count"] == 1
        assert result["seen_tool_calls"] == first["seen_tool_calls"]
    assert first == before


def test_injected_dtc_tool_must_be_callable():
    with pytest.raises(ValueError, match="dtc_lookup"):
        build_diagnosis_graph(dtc_lookup="not callable")


def test_invalid_direct_adapter_input_is_rejected_before_connection(monkeypatch):
    calls = fake_connection(monkeypatch, result=CallToolResult(content=[], structured_content=payload()))
    with pytest.raises(ValueError):
        adapter.lookup_dtc_via_mcp("   ", "P0AA6")
    assert calls == []
