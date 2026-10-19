from copy import deepcopy

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from app import tool_router
from app.diagnosis_graph import build_diagnosis_graph
from app.tool_router import ToolExecutionFailed, execute_tool_call
from scripts.run_diagnosis_demo import make_state


FAILURES = [
    (TimeoutError, "tool_timeout"),
    (ConnectionError, "tool_unavailable"),
    (LookupError, "tool_data_not_found"),
]


def make_call():
    return {"tool_name": "lookup_dtc", "arguments": {
        "vehicle_id": "VIN-DEMO-001", "dtc_code": "P0AA6",
    }}


@pytest.mark.parametrize("error_type, reason", FAILURES)
def test_router_records_known_failures_and_preserves_the_original_cause(monkeypatch, error_type, reason):
    cause = error_type("教学注入的工具故障")
    def fail(**arguments):
        raise cause

    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", fail)
    trace = []
    with pytest.raises(ToolExecutionFailed) as raised:
        execute_tool_call(make_call(), trace)
    assert raised.value.reason == reason
    assert raised.value.__cause__ is cause
    assert trace == [{
        "tool_name": "lookup_dtc", "status": "error", "reason": reason,
        "error_type": error_type.__name__, "message": str(cause),
    }]


@pytest.mark.parametrize("error_type", [RuntimeError, KeyError, IndexError, ValueError])
def test_program_errors_are_not_disguised_as_expected_tool_failures(monkeypatch, error_type):
    cause = error_type("模拟程序缺陷")
    def fail(**arguments):
        raise cause

    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", fail)
    trace = []
    with pytest.raises(error_type) as raised:
        execute_tool_call(make_call(), trace)
    assert raised.value is cause
    assert not isinstance(raised.value, ToolExecutionFailed)
    assert trace == []


@pytest.mark.parametrize("tool", ["lookup_dtc", "lookup_vehicle_history", "lookup_inventory"])
@pytest.mark.parametrize("error_type, reason", FAILURES)
def test_known_failures_stop_the_graph_and_prepare_a_handoff(monkeypatch, tool, error_type, reason):
    entered = []
    def fail(**arguments):
        entered.append(arguments)
        raise error_type("测试工具故障")

    monkeypatch.setitem(tool_router.TOOL_REGISTRY, tool, fail)
    inputs = make_state([], requested_tool=tool, citations=[{"chunk_id": "old"}],
                        retrieved_chunks=[{"text": "old"}], retrieval_query="old")
    before = deepcopy(inputs)
    result = build_diagnosis_graph().invoke(inputs)

    assert len(entered) == 1
    assert result["status"] == "needs_human"
    assert result["next_action"] == "handoff_to_human"
    assert result["stop_reason"] == reason
    assert result["tool_result"] is None
    assert result["tool_call_count"] == 1
    assert len(result["seen_tool_calls"]) == 1
    assert result["citations"] == []
    assert result["retrieved_chunks"] == []
    assert result["retrieval_query"] == ""
    assert "请人工复核" in result["answer"]
    assert result["trace"] == [
        "check_information_completeness", "route_selected_tool", "handoff_to_human",
    ]
    assert result["tool_trace"] == [{
        "tool_name": tool, "status": "error", "reason": reason,
        "error_type": error_type.__name__, "message": "测试工具故障",
    }]
    assert result["handoff_request"] == {
        "reason": reason,
        "vehicle_id": inputs["vehicle_id"], "symptom": inputs["symptom"],
        "dtc_codes": inputs["dtc_codes"],
        "failed_tool_call": result["tool_call"],
        "error": result["tool_trace"][0], "tool_call_count": 1,
    }
    assert inputs == before


@pytest.mark.parametrize("error_type, reason", FAILURES)
def test_checkpoint_preserves_failed_budget_and_prevents_automatic_repeat(tmp_path, monkeypatch, error_type, reason):
    entered = []
    def fail(**arguments):
        entered.append(arguments)
        raise error_type("工具故障")

    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", fail)
    database = str(tmp_path / "diagnosis.sqlite")
    config = {"configurable": {"thread_id": "failed-call"}}
    with SqliteSaver.from_conn_string(database) as saver:
        first = build_diagnosis_graph(saver).invoke(make_state([]), config)
        before = deepcopy(first)

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_diagnosis_graph(saver)
        assert graph.get_state(config).values == first
        assert first["handoff_request"]["reason"] == reason
        repeated = graph.invoke({"requested_tool": "lookup_dtc"}, config)
        assert repeated["status"] == "stopped"
        assert repeated["stop_reason"] == "duplicate_tool_call"
        assert repeated["tool_call_count"] == 1
        assert repeated["seen_tool_calls"] == first["seen_tool_calls"]
        assert repeated["handoff_request"] is None
        assert repeated["tool_trace"] == [*first["tool_trace"], {
            "tool_name": "lookup_dtc", "status": "rejected", "reason": "duplicate_tool_call",
        }]
    assert len(entered) == 1
    assert first == before


@pytest.mark.parametrize("overrides", [
    {}, {"dtc_codes": []}, {"tool_call_count": 2},
])
def test_other_paths_clear_a_stale_handoff_request(overrides):
    result = build_diagnosis_graph().invoke(make_state(
        [], handoff_request={"reason": "old_error"}, **overrides,
    ))
    assert result["handoff_request"] is None
    assert "handoff_to_human" not in result["trace"]


def test_handoff_payload_is_independent_of_the_live_trace_and_inputs(monkeypatch):
    def fail(**arguments):
        raise TimeoutError("工具超时")
    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", fail)
    inputs = make_state([])
    result = build_diagnosis_graph().invoke(inputs)
    result["handoff_request"]["dtc_codes"].append("P0123")
    result["handoff_request"]["error"]["message"] = "修改展示信息"
    result["handoff_request"]["failed_tool_call"]["arguments"]["dtc_code"] = "P0123"
    assert result["dtc_codes"] == ["P0AA6"]
    assert inputs["dtc_codes"] == ["P0AA6"]
    assert result["tool_trace"][0]["message"] == "工具超时"
    assert result["tool_call"]["arguments"]["dtc_code"] == "P0AA6"


def test_unknown_code_in_the_real_mock_catalog_returns_a_review_request():
    result = build_diagnosis_graph().invoke(make_state([], dtc_codes=["P0123"]))
    assert result["status"] == "needs_human"
    assert result["stop_reason"] == "tool_data_not_found"
    assert result["tool_call_count"] == 1
    assert result["handoff_request"]["dtc_codes"] == ["P0123"]
    assert result["tool_trace"][0]["message"] == "DTC 未找到：P0123"
    assert result["citations"] == []
