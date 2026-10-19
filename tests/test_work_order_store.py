from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.work_order_draft import build_work_order_draft
from app.work_order_graph import build_work_order_graph
from app.work_order_review import apply_work_order_decision
from app.work_order_store import create_work_order_once


def make_state(decision=None):
    draft = build_work_order_draft({
        "vehicle_id": "VIN-DEMO-001", "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
    })
    decision = {"action": "approve"} if decision is None else decision
    reviewed = apply_work_order_decision(draft, decision)
    return {
        "draft": reviewed, "status": reviewed["status"], "review_error": None,
        "review_history": [{
            "decision": decision, "status": reviewed["status"],
            "error": None, "draft": deepcopy(reviewed),
        }],
    }


def rows(database):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(
            "SELECT work_order_id, idempotency_key, status, approved_draft_json FROM work_orders"
        ).fetchall()


def submit(state, database, key="work-order:request-001"):
    return create_work_order_once(state, idempotency_key=key, database_path=database)


def test_creates_one_open_order_with_the_exact_approved_snapshot(tmp_path):
    state = make_state()
    before = deepcopy(state)
    database = tmp_path / "orders.sqlite"
    record = submit(state, database)
    assert record["work_order_id"]
    assert record["status"] == "open"
    assert record["draft"] == state["draft"]
    assert record["idempotency_key"] == "work-order:request-001"
    assert len(rows(database)) == 1
    assert state == before
    record["draft"]["dtc_codes"].append("P0123")
    assert submit(state, database)["draft"] == before["draft"]


def test_same_request_and_content_return_the_same_order_despite_key_order(tmp_path):
    state = make_state()
    database = tmp_path / "orders.sqlite"
    first = submit(state, database)
    reordered = deepcopy(state)
    reordered["draft"] = dict(reversed(list(reordered["draft"].items())))
    assert submit(reordered, database) == first
    assert len(rows(database)) == 1


def test_same_key_with_different_approved_content_is_a_conflict(tmp_path):
    database = tmp_path / "orders.sqlite"
    first = submit(make_state(), database)
    changed = make_state()
    changed["draft"]["description"] = "人工批准的另一份内容"
    changed["review_history"][-1]["draft"] = deepcopy(changed["draft"])
    with pytest.raises(ValueError, match="内容不一致"):
        submit(changed, database)
    assert len(rows(database)) == 1
    assert json.loads(rows(database)[0][3]) == first["draft"]


def test_distinct_request_keys_create_distinct_orders(tmp_path):
    database = tmp_path / "orders.sqlite"
    first = submit(make_state(), database, key="request-a")
    second = submit(make_state(), database, key="request-b")
    assert first["work_order_id"] != second["work_order_id"]
    assert len(rows(database)) == 2


@pytest.mark.parametrize("decision", [
    {"action": "edit", "changes": {"title": "继续等待审批"}},
    {"action": "reject", "reason": "信息有误"},
])
def test_pending_or_rejected_state_cannot_even_create_the_database(tmp_path, decision):
    database = tmp_path / "not-created" / "orders.sqlite"
    with pytest.raises(ValueError, match="已批准"):
        submit(make_state(decision), database)
    assert not database.parent.exists()


def test_approved_state_label_cannot_override_an_unapproved_draft(tmp_path):
    state = make_state()
    state["draft"]["status"] = "pending_approval"
    database = tmp_path / "orders.sqlite"
    with pytest.raises(ValueError, match="草稿状态"):
        submit(state, database)
    assert not database.exists()


@pytest.mark.parametrize("corruption", [
    "missing_history", "wrong_action", "history_error", "review_error", "changed_draft",
])
def test_requires_a_matching_final_approval(tmp_path, corruption):
    state = make_state()
    if corruption == "missing_history":
        state["review_history"] = []
    elif corruption == "wrong_action":
        state["review_history"][-1]["decision"] = {"action": "edit"}
    elif corruption == "history_error":
        state["review_history"][-1]["error"] = "校验未通过"
    elif corruption == "review_error":
        state["review_error"] = "校验未通过"
    else:
        state["draft"]["description"] = "批准后被替换的内容"
    database = tmp_path / "orders.sqlite"
    with pytest.raises(ValueError, match="批准记录"):
        submit(state, database)
    assert not database.exists()


@pytest.mark.parametrize("field, value", [
    ("title", "   "), ("dtc_codes", []),
])
def test_invalid_approved_content_is_not_written(tmp_path, field, value):
    state = make_state()
    state["draft"][field] = value
    state["review_history"][-1]["draft"] = deepcopy(state["draft"])
    database = tmp_path / "orders.sqlite"
    with pytest.raises(ValueError, match=field):
        submit(state, database)
    assert not database.exists()


@pytest.mark.parametrize("key", [None, "   ", 123])
def test_invalid_idempotency_key_is_not_written(tmp_path, key):
    database = tmp_path / "orders.sqlite"
    with pytest.raises(ValueError, match="idempotency_key"):
        submit(make_state(), database, key=key)
    assert not database.exists()


def test_concurrent_retries_create_only_one_order(tmp_path):
    database = tmp_path / "orders.sqlite"
    state = make_state()
    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(executor.map(lambda _: submit(state, database), range(4)))
    assert all(record == records[0] for record in records)
    assert len(rows(database)) == 1


def test_retry_after_process_exits_following_commit_returns_the_existing_order(tmp_path):
    database = tmp_path / "orders.sqlite"
    state = make_state()
    program = """
import json
import os
import sys
from app.work_order_store import create_work_order_once
create_work_order_once(json.load(sys.stdin), idempotency_key='work-order:request-001', database_path=sys.argv[1])
os._exit(17)
"""
    process = subprocess.run(
        [sys.executable, "-c", program, str(database)],
        input=json.dumps(state), text=True, capture_output=True,
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )
    assert process.returncode == 17, process.stderr
    committed_id = rows(database)[0][0]
    retried = submit(state, database)
    assert retried["work_order_id"] == committed_id
    assert len(rows(database)) == 1


def test_real_graph_must_approve_the_edited_content_before_submission(tmp_path):
    database = tmp_path / "orders.sqlite"
    config = {"configurable": {"thread_id": "approval-a"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite")) as saver:
        graph = build_work_order_graph(saver)
        graph.invoke({
            "vehicle_id": "VIN-DEMO-001", "symptom": "仪表提示绝缘故障", "dtc_codes": ["P0AA6"],
        }, config)
        with pytest.raises(ValueError, match="已批准"):
            submit(graph.get_state(config).values, database)
        graph.invoke(Command(resume={"action": "edit", "changes": {
            "description": "请先联系用户确认故障出现时间。",
        }}), config)
        with pytest.raises(ValueError, match="已批准"):
            submit(graph.get_state(config).values, database)
        assert not database.exists()
        graph.invoke(Command(resume={"action": "approve"}), config)
        record = submit(graph.get_state(config).values, database)
        assert record["draft"]["description"] == "请先联系用户确认故障出现时间。"
        assert record["draft"] == graph.get_state(config).values["draft"]
        assert submit(graph.get_state(config).values, database) == record
        assert len(rows(database)) == 1
