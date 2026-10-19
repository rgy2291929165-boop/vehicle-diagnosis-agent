import pytest

from app.tool_planner import build_tool_call


def make_state(**overrides) -> dict:
    state = {
        "vehicle_id": "VIN-DEMO-001",
        "dtc_codes": ["P0AA6"],
        "part_number": "HV-ISO-SENSOR-01",
    }
    state.update(overrides)
    return state


def test_planner_builds_dtc_call_from_diagnosis_state():
    call = build_tool_call("lookup_dtc", make_state())

    assert call == {
        "tool_name": "lookup_dtc",
        "arguments": {
            "vehicle_id": "VIN-DEMO-001",
            "dtc_code": "P0AA6",
        },
    }


def test_planner_builds_vehicle_history_call():
    call = build_tool_call("lookup_vehicle_history", make_state())

    assert call == {
        "tool_name": "lookup_vehicle_history",
        "arguments": {
            "vehicle_id": "VIN-DEMO-001",
        },
    }


def test_planner_builds_inventory_call():
    call = build_tool_call("lookup_inventory", make_state())

    assert call == {
        "tool_name": "lookup_inventory",
        "arguments": {
            "part_number": "HV-ISO-SENSOR-01",
        },
    }


def test_planner_rejects_unknown_tool():
    with pytest.raises(PermissionError):
        build_tool_call("delete_work_order", make_state())


def test_planner_rejects_missing_data_for_requested_tool():
    with pytest.raises(ValueError, match="dtc_codes"):
        build_tool_call("lookup_dtc", make_state(dtc_codes=[]))