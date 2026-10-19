from copy import deepcopy

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app import work_order_graph
from app.work_order_graph import build_work_order_graph


def make_input():
    return {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
    }


def config_for(thread_id="approval-001"):
    return {"configurable": {"thread_id": thread_id}}


def test_graph_pauses_before_a_decision_and_exposes_an_independent_draft(tmp_path):
    inputs = make_input()
    before = deepcopy(inputs)
    with SqliteSaver.from_conn_string(str(tmp_path / "approval.sqlite")) as saver:
        graph = build_work_order_graph(saver)
        result = graph.invoke(inputs, config_for())
        assert result["status"] == "pending_approval"
        assert result["draft"]["status"] == "pending_approval"
        assert result["review_history"] == []
        assert result["trace"] == ["prepare_work_order_draft"]
        assert graph.get_state(config_for()).next == ("review_work_order",)
        payload = result["__interrupt__"][0].value
        assert payload == {
            "kind": "work_order_approval",
            "draft": result["draft"],
            "actions": ["approve", "edit", "reject"],
            "error": None,
        }
        payload["draft"]["title"] = "仅修改展示副本"
        assert graph.get_state(config_for()).values["draft"]["title"] == "车辆故障人工复核"
    assert inputs == before


@pytest.mark.parametrize("decision, expected_status", [
    ({"action": "approve"}, "approved"),
    ({"action": "reject", "reason": "需要重新确认信息"}, "rejected"),
])
def test_reopened_database_resumes_a_pending_review(tmp_path, decision, expected_status):
    database = str(tmp_path / "approval.sqlite")
    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        paused = graph.invoke(make_input(), config_for())
        saved = graph.get_state(config_for()).values

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        assert graph.get_state(config_for()).values == saved
        result = graph.invoke(Command(resume=decision), config_for())
        assert result["status"] == expected_status
        assert result["draft"]["status"] == expected_status
        assert not result.get("__interrupt__")
        assert graph.get_state(config_for()).next == ()
        assert result["trace"] == ["prepare_work_order_draft", "review_work_order"]
        assert result["review_history"] == [{
            "decision": decision, "status": expected_status,
            "error": None, "draft": result["draft"],
        }]
        if expected_status == "rejected":
            assert result["draft"]["rejection_reason"] == decision["reason"]
    assert paused["draft"]["status"] == "pending_approval"


def test_edit_pauses_again_and_reopened_graph_approves_the_edited_content(tmp_path):
    database = str(tmp_path / "approval.sqlite")
    decision = {"action": "edit", "changes": {"description": "请先联系用户确认故障出现时间。"}}
    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        original = graph.invoke(make_input(), config_for())
        original_draft = deepcopy(original["draft"])

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        edited = graph.invoke(Command(resume=decision), config_for())
        assert edited["status"] == "pending_approval"
        assert edited["draft"]["description"] == decision["changes"]["description"]
        assert edited["__interrupt__"][0].value["draft"] == edited["draft"]
        assert edited["__interrupt__"][0].id != original["__interrupt__"][0].id
        assert edited["review_history"][0]["decision"] == decision
        assert edited["review_history"][0]["draft"] == edited["draft"]

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        approved = graph.invoke(Command(resume={"action": "approve"}), config_for())
        assert approved["draft"] == {**edited["draft"], "status": "approved"}
        assert len(approved["review_history"]) == 2
        assert approved["review_history"][0] == edited["review_history"][0]
        assert approved["review_history"][1]["draft"] == approved["draft"]
        assert approved["trace"] == [
            "prepare_work_order_draft", "review_work_order", "review_work_order",
        ]
        assert graph.get_state(config_for()).next == ()
    assert original["draft"] == original_draft
    assert edited["draft"]["status"] == "pending_approval"


@pytest.mark.parametrize("decision", [
    {"action": "delete"},
    {"action": "edit", "changes": {"status": "approved"}},
    {"action": "approve", "changes": {"title": "夹带修改"}},
])
def test_invalid_decision_pauses_again_and_can_be_corrected_after_reopening(tmp_path, decision):
    database = str(tmp_path / "approval.sqlite")
    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        initial = graph.invoke(make_input(), config_for())
        invalid = graph.invoke(Command(resume=decision), config_for())
        assert invalid["status"] == "pending_approval"
        assert invalid["draft"] == initial["draft"]
        assert invalid["review_error"]
        assert invalid["__interrupt__"][0].value["error"] == invalid["review_error"]
        assert invalid["review_history"][0]["status"] == "invalid"
        assert invalid["review_history"][0]["decision"] == decision

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_work_order_graph(saver)
        corrected = graph.invoke(Command(resume={"action": "approve"}), config_for())
        assert corrected["status"] == "approved"
        assert corrected["review_error"] is None
        assert [item["status"] for item in corrected["review_history"]] == ["invalid", "approved"]
        assert graph.get_state(config_for()).next == ()


def test_reviewing_one_thread_does_not_approve_another_thread(tmp_path):
    with SqliteSaver.from_conn_string(str(tmp_path / "approval.sqlite")) as saver:
        graph = build_work_order_graph(saver)
        graph.invoke(make_input(), config_for("a"))
        graph.invoke(make_input(), config_for("b"))
        untouched = deepcopy(graph.get_state(config_for("b")).values)
        graph.invoke(Command(resume={"action": "approve"}), config_for("a"))
        assert graph.get_state(config_for("a")).values["status"] == "approved"
        assert graph.get_state(config_for("b")).values == untouched
        assert graph.get_state(config_for("b")).next == ("review_work_order",)


def test_checkpointer_is_required():
    with pytest.raises(ValueError, match="checkpointer"):
        build_work_order_graph(None)


def test_unexpected_program_error_is_not_reported_as_an_invalid_decision(tmp_path, monkeypatch):
    def broken_review(draft, decision):
        raise RuntimeError("模拟程序错误")

    with SqliteSaver.from_conn_string(str(tmp_path / "approval.sqlite")) as saver:
        graph = build_work_order_graph(saver)
        graph.invoke(make_input(), config_for())
        monkeypatch.setattr(work_order_graph, "apply_work_order_decision", broken_review)
        with pytest.raises(RuntimeError, match="模拟程序错误"):
            graph.invoke(Command(resume={"action": "approve"}), config_for())
