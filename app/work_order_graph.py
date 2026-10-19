"""工单人工审批图：持久化暂停/恢复，尚不写入正式工单。"""

from copy import deepcopy
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.work_order_draft import build_work_order_draft
from app.work_order_review import apply_work_order_decision


class WorkOrderState(TypedDict):
    vehicle_id: str
    symptom: str
    dtc_codes: list[str]
    draft: dict
    status: str
    review_error: str | None
    review_history: list[dict]
    trace: list[str]


def prepare_work_order_draft(state: WorkOrderState) -> dict:
    return {
        "draft": build_work_order_draft(state),
        "status": "pending_approval",
        "review_error": None,
        "review_history": [],
        "trace": ["prepare_work_order_draft"],
    }


def review_work_order(state: WorkOrderState) -> dict:
    # 恢复时本节点从头执行；interrupt 之前只展示信息，不执行写入。
    decision = interrupt({
        "kind": "work_order_approval",
        "draft": deepcopy(state["draft"]),
        "actions": ["approve", "edit", "reject"],
        "error": state["review_error"],
    })

    try:
        reviewed = apply_work_order_decision(state["draft"], decision)
    except ValueError as error:
        reviewed = deepcopy(state["draft"])
        review_error = str(error)
        history_status = "invalid"
    else:
        review_error = None
        history_status = reviewed["status"]

    return {
        "draft": reviewed,
        "status": reviewed["status"],
        "review_error": review_error,
        "review_history": [*state["review_history"], {
            "decision": deepcopy(decision),
            "status": history_status,
            "error": review_error,
            "draft": deepcopy(reviewed),
        }],
        "trace": [*state["trace"], "review_work_order"],
    }


def choose_after_review(state: WorkOrderState) -> Literal["again", "finish"]:
    if state["status"] == "pending_approval":
        return "again"
    return "finish"


def build_work_order_graph(checkpointer):
    if checkpointer is None:
        raise ValueError("审批图必须提供 checkpointer 才能暂停和恢复")

    builder = StateGraph(WorkOrderState)
    builder.add_node("prepare_work_order_draft", prepare_work_order_draft)
    builder.add_node("review_work_order", review_work_order)
    builder.add_edge(START, "prepare_work_order_draft")
    builder.add_edge("prepare_work_order_draft", "review_work_order")
    builder.add_conditional_edges("review_work_order", choose_after_review, {
        "again": "review_work_order",
        "finish": END,
    })
    return builder.compile(checkpointer=checkpointer)
