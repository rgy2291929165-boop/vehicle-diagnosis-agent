from copy import deepcopy

import pytest

from app.work_order_draft import build_work_order_draft
from app.work_order_review import apply_work_order_decision


def make_draft():
    return build_work_order_draft({
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
    })


def test_approve_changes_only_the_status():
    draft = make_draft()
    result = apply_work_order_decision(draft, {"action": "approve"})
    assert result == {**draft, "status": "approved"}


def test_edit_requires_separate_approval_of_the_changed_content():
    draft = make_draft()
    edited = apply_work_order_decision(draft, {
        "action": "edit",
        "changes": {
            "title": " 车辆故障待人工核实 ",
            "description": " 请联系用户确认故障出现时间。 ",
        },
    })

    assert edited["status"] == "pending_approval"
    assert edited["title"] == "车辆故障待人工核实"
    assert edited["description"] == "请联系用户确认故障出现时间。"
    for name in ("vehicle_id", "symptom", "dtc_codes"):
        assert edited[name] == draft[name]

    approved = apply_work_order_decision(edited, {"action": "approve"})
    assert approved == {**edited, "status": "approved"}
    assert edited["status"] == "pending_approval"


def test_reject_records_the_reason():
    draft = make_draft()
    rejected = apply_work_order_decision(draft, {
        "action": "reject", "reason": " 信息需要重新确认 ",
    })
    assert rejected == {
        **draft, "status": "rejected", "rejection_reason": "信息需要重新确认",
    }


@pytest.mark.parametrize("decision", [
    {"action": "approve"},
    {"action": "edit", "changes": {"title": "人工核实"}},
    {"action": "reject", "reason": "信息有误"},
])
def test_decision_preserves_inputs_and_returns_independent_lists(decision):
    draft = make_draft()
    original_draft, original_decision = deepcopy(draft), deepcopy(decision)
    result = apply_work_order_decision(draft, decision)
    result["dtc_codes"].append("P0123")
    assert draft == original_draft
    assert decision == original_decision


@pytest.mark.parametrize("status", ["approved", "rejected", "running", None])
def test_cannot_review_a_draft_outside_pending_approval(status):
    draft = {**make_draft(), "status": status}
    with pytest.raises(ValueError, match="pending_approval"):
        apply_work_order_decision(draft, {"action": "approve"})


@pytest.mark.parametrize("decision", [None, [], "approve"])
def test_decision_must_be_a_dictionary(decision):
    with pytest.raises(ValueError, match="decision"):
        apply_work_order_decision(make_draft(), decision)


@pytest.mark.parametrize("decision", [{}, {"action": "delete"}, {"action": []}])
def test_action_must_be_supported(decision):
    with pytest.raises(ValueError, match="action"):
        apply_work_order_decision(make_draft(), decision)


@pytest.mark.parametrize("decision", [
    {"action": "approve", "changes": {"title": "夹带修改"}},
    {"action": "edit"},
    {"action": "reject"},
    {"action": "reject", "reason": "信息有误", "extra": True},
])
def test_rejects_missing_or_unexpected_decision_fields(decision):
    with pytest.raises(ValueError, match="决策字段"):
        apply_work_order_decision(make_draft(), decision)


@pytest.mark.parametrize("changes", [
    None, {}, [],
    {"vehicle_id": "VIN-OTHER"},
    {"status": "approved"},
    {"title": "正常修改", "dtc_codes": ["P0123"]},
])
def test_edit_rejects_invalid_changes_without_partial_updates(changes):
    draft = make_draft()
    before = deepcopy(draft)
    with pytest.raises(ValueError, match="changes"):
        apply_work_order_decision(draft, {"action": "edit", "changes": changes})
    assert draft == before


@pytest.mark.parametrize("field, value", [
    ("title", "   "), ("description", "   "), ("description", 123),
])
def test_edit_requires_nonempty_text(field, value):
    with pytest.raises(ValueError, match=field):
        apply_work_order_decision(make_draft(), {
            "action": "edit", "changes": {field: value},
        })


@pytest.mark.parametrize("reason", [None, "   ", 123])
def test_reject_requires_a_text_reason(reason):
    with pytest.raises(ValueError, match="reason"):
        apply_work_order_decision(make_draft(), {"action": "reject", "reason": reason})
