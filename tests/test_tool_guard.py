import pytest

from app import tool_guard, tool_router


def make_call():
    return {
        "tool_name": "lookup_dtc",
        "arguments": {
            "vehicle_id": "VIN-DEMO-001",
            "dtc_code": "P0AA6",
        },
    }


def make_run_state(**overrides):
    state = {
        "tool_call_count": 0,
        "max_tool_calls": 2,
        "tool_trace": [],
        "seen_tool_calls": [],
    }
    state.update(overrides)
    return state


def test_successful_call_consumes_one_unit_of_budget():
    state = make_run_state()

    result = tool_guard.execute_guarded_tool_call(make_call(), state)

    assert result["dtc_code"] == "P0AA6"
    assert state["tool_call_count"] == 1
    assert state["tool_trace"] == [
        {"tool_name": "lookup_dtc", "status": "success"}
    ]


def test_exhausted_budget_rejects_before_entering_tool(monkeypatch):
    state = make_run_state(tool_call_count=2)
    entered = []

    def fake_tool(**arguments):
        entered.append(arguments)
        return {}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        "lookup_dtc",
        fake_tool,
    )

    with pytest.raises(RuntimeError, match="调用次数"):
        tool_guard.execute_guarded_tool_call(make_call(), state)

    assert entered == []
    assert state["tool_call_count"] == 2
    assert state["tool_trace"] == [
        {
            "tool_name": "lookup_dtc",
            "status": "rejected",
            "reason": "tool_call_limit",
        }
    ]

def test_duplicate_call_is_rejected_even_if_argument_order_changes(monkeypatch):
    state = make_run_state()
    entered = []

    def fake_tool(**arguments):
        entered.append(arguments)
        return {"dtc_code": arguments["dtc_code"]}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        "lookup_dtc",
        fake_tool,
    )

    tool_guard.execute_guarded_tool_call(make_call(), state)

    repeated_call = {
        "tool_name": "lookup_dtc",
        "arguments": {
            "dtc_code": "P0AA6",
            "vehicle_id": "VIN-DEMO-001",
        },
    }

    with pytest.raises(RuntimeError, match="重复调用"):
        tool_guard.execute_guarded_tool_call(repeated_call, state)

    assert len(entered) == 1
    assert state["tool_call_count"] == 1
    assert len(state["seen_tool_calls"]) == 1
    assert state["tool_trace"][-1] == {
        "tool_name": "lookup_dtc",
        "status": "rejected",
        "reason": "duplicate_tool_call",
    }


def test_same_tool_with_different_arguments_is_allowed(monkeypatch):
    state = make_run_state()
    entered = []

    def fake_tool(**arguments):
        entered.append(arguments)
        return {"dtc_code": arguments["dtc_code"]}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        "lookup_dtc",
        fake_tool,
    )

    tool_guard.execute_guarded_tool_call(make_call(), state)

    different_call = make_call()
    different_call["arguments"]["dtc_code"] = "P0123"
    result = tool_guard.execute_guarded_tool_call(different_call, state)

    assert result["dtc_code"] == "P0123"
    assert len(entered) == 2
    assert state["tool_call_count"] == 2
    assert len(state["seen_tool_calls"]) == 2