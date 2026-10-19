"""第三周 Day 2：验证诊断信息完整性检查。"""

from copy import deepcopy

from app.diagnosis_state import DiagnosisState, check_information_completeness


def make_state(**overrides) -> DiagnosisState:
    state: DiagnosisState = {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
        "missing_fields": [],
        "next_action": "ask_clarifying_question",
        "clarifying_question": None,
        "trace": [],
    }
    state.update(overrides)
    return state


def test_complete_information_routes_to_tools_without_a_question():
    update = check_information_completeness(make_state())

    assert update["missing_fields"] == []
    assert update["next_action"] == "route_tools"
    assert update["clarifying_question"] is None
    assert update["trace"] == ["check_information_completeness"]


def test_missing_dtc_must_ask_before_tools_are_routed():
    update = check_information_completeness(make_state(dtc_codes=[]))

    assert update["missing_fields"] == ["dtc_codes"]
    assert update["next_action"] == "ask_clarifying_question"
    assert "故障码（DTC）" in update["clarifying_question"]

def test_blank_dtc_must_ask_before_tools_are_routed():
    update = check_information_completeness(make_state(dtc_codes=["   "]))

    assert update["missing_fields"] == ["dtc_codes"]
    assert update["next_action"] == "ask_clarifying_question"
    assert "故障码（DTC）" in update["clarifying_question"]

def test_question_lists_every_missing_field_in_a_stable_order():
    update = check_information_completeness(
        make_state(vehicle_id=" ", symptom=None, dtc_codes=[" "])
    )

    assert update["missing_fields"] == ["vehicle_id", "symptom", "dtc_codes"]
    assert update["clarifying_question"] == (
        "请补充以下诊断信息：车辆标识（vehicle_id）、故障现象（symptom）、故障码（DTC）。"
    )


def test_completeness_check_does_not_mutate_the_input_state():
    state = make_state(dtc_codes=[])
    original_state = deepcopy(state)

    check_information_completeness(state)

    assert state == original_state
