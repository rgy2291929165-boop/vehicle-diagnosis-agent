from copy import deepcopy

import pytest

from app.work_order_draft import build_work_order_draft


def make_state(**overrides):
    state = {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
    }
    state.update(overrides)
    return state


def test_builds_pending_draft_and_normalizes_user_input():
    draft = build_work_order_draft(make_state(
        vehicle_id=" VIN-DEMO-001 ",
        symptom=" 仪表提示绝缘故障 ",
        dtc_codes=[" p0aa6 ", " p0123 "],
    ))

    assert draft == {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6", "P0123"],
        "title": "车辆故障人工复核",
        "description": (
            "用户报告的故障现象：仪表提示绝缘故障。"
            "用户提供的故障码：P0AA6、P0123。"
            "请人工核实故障信息并安排后续检查。"
        ),
        "status": "pending_approval",
    }


def test_draft_does_not_modify_or_share_the_input_codes():
    state = make_state(dtc_codes=[" p0aa6 "])
    before = deepcopy(state)

    draft = build_work_order_draft(state)
    assert state == before

    draft["dtc_codes"].append("P0123")
    assert state == before


def test_no_evidence_can_request_review_without_copying_tool_advice():
    state = make_state(
        status="no_evidence",
        citations=[],
        answer="未经证据支持的建议：立即更换传感器。",
        tool_result={"recommended_check": "立即更换传感器"},
    )

    draft = build_work_order_draft(state)

    assert draft["status"] == "pending_approval"
    assert draft["title"] == "车辆故障人工复核"
    assert "请人工核实" in draft["description"]
    assert "更换传感器" not in draft["description"]
    assert "dtc_codes" in draft


@pytest.mark.parametrize("field, value", [
    ("vehicle_id", None),
    ("vehicle_id", "   "),
    ("vehicle_id", 123),
    ("symptom", None),
    ("symptom", "   "),
    ("symptom", []),
    ("dtc_codes", None),
    ("dtc_codes", []),
    ("dtc_codes", "P0AA6"),
    ("dtc_codes", ["   "]),
    ("dtc_codes", ["P0AA6", None]),
    ("dtc_codes", [123]),
])
def test_rejects_invalid_required_fields(field, value):
    with pytest.raises(ValueError, match=field):
        build_work_order_draft(make_state(**{field: value}))


@pytest.mark.parametrize("field", ["vehicle_id", "symptom", "dtc_codes"])
def test_rejects_missing_required_fields(field):
    state = make_state()
    del state[field]

    with pytest.raises(ValueError, match=field):
        build_work_order_draft(state)
