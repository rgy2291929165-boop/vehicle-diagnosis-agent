import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from app import tool_router
from app.diagnosis_graph import build_diagnosis_graph
from scripts.run_diagnosis_demo import make_state


def make_checkpoint_state(**overrides):
    chunks = [{
        "chunk_id": "checkpoint:0",
        "document_id": "checkpoint",
        "text": "P0AA6 教学片段，仅用于验证 checkpoint 状态恢复。",
        "source": "demo/checkpoint-fixture",
    }]
    return make_state(chunks, **overrides)


def test_reopened_database_restores_state_and_accepts_partial_input(tmp_path):
    database = str(tmp_path / "diagnosis.sqlite")
    config = {"configurable": {"thread_id": "diagnosis-001"}}

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        first = graph.invoke(make_checkpoint_state(dtc_codes=[]), config)
        assert first["status"] == "needs_info"
        assert first["tool_call_count"] == 0

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        assert graph.get_state(config).values == first
        second = graph.invoke({"dtc_codes": ["P0AA6"]}, config)
        assert second["status"] == "ok"
        assert second["tool_call_count"] == 1
        assert second["missing_fields"] == []
        assert second["clarifying_question"] is None
        assert second["citations"] == [{
            "chunk_id": "checkpoint:0",
            "document_id": "checkpoint",
            "source": "demo/checkpoint-fixture",
        }]
        assert graph.get_state(config).values == second


def test_thread_ids_keep_conversations_separate(tmp_path):
    database = str(tmp_path / "diagnosis.sqlite")
    config_a = {"configurable": {"thread_id": "conversation-a"}}
    config_b = {"configurable": {"thread_id": "conversation-b"}}

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        first = graph.invoke(make_checkpoint_state(dtc_codes=[]), config_a)
        second = graph.invoke(make_checkpoint_state(), config_b)
        assert first["status"] == "needs_info"
        assert first["tool_call_count"] == 0
        assert second["status"] == "ok"
        assert second["tool_call_count"] == 1
        assert graph.get_state(config_a).values == first
        assert graph.get_state(config_b).values == second


@pytest.mark.parametrize("tool_name, limit, reason", [
    ("lookup_dtc", 2, "duplicate_tool_call"),
    ("lookup_inventory", 1, "tool_call_limit"),
])
def test_reopened_database_preserves_tool_guards(
    tmp_path, monkeypatch, tool_name, limit, reason,
):
    database = str(tmp_path / "diagnosis.sqlite")
    config = {"configurable": {"thread_id": "guard-test"}}

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        first = graph.invoke(make_checkpoint_state(
            requested_tool=tool_name, max_tool_calls=limit,
        ), config)
        assert first["status"] == "ok"
        assert first["tool_call_count"] == 1

    def forbidden_tool(**arguments):
        pytest.fail("被拦截的工具不应执行")

    monkeypatch.setitem(tool_router.TOOL_REGISTRY, tool_name, forbidden_tool)

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        result = graph.invoke({"requested_tool": tool_name}, config)
        assert result["status"] == "stopped"
        assert result["stop_reason"] == reason
        assert result["tool_call_count"] == 1
        assert result["max_tool_calls"] == limit
        assert result["tool_result"] is None
        assert result["citations"] == []
        assert result["seen_tool_calls"] == first["seen_tool_calls"]
        assert result["tool_trace"] == [*first["tool_trace"], {
            "tool_name": tool_name,
            "status": "rejected",
            "reason": reason,
        }]
        assert graph.get_state(config).values == result
