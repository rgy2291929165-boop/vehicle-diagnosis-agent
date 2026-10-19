"""第三周 Day 5：使用结构化规划和受限工具路由的无 LLM 诊断图。"""

from __future__ import annotations

from copy import deepcopy
from functools import partial
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from app.bm25 import tokenize
from app.diagnosis_state import (
    FIELD_LABELS,
    check_information_completeness,
)
from app.tool_planner import build_tool_call
from app.tool_guard import ToolCallRejected, execute_guarded_tool_call
from app.tool_router import ToolExecutionFailed
from app.knowledge_retrieval import search_knowledge

class DiagnosisGraphState(TypedDict):
    vehicle_id: str | None
    symptom: str | None
    dtc_codes: list[str]
    part_number: str | None
    requested_tool: str
    missing_fields: list[str]
    next_action: str
    clarifying_question: str | None
    tool_call: dict | None
    tool_result: dict | None
    tool_trace: list[dict]
    answer: str
    trace: list[str]
    tool_call_count: int
    max_tool_calls: int
    seen_tool_calls: list[str]
    status: str
    stop_reason: str | None
    knowledge_chunks: list[dict]
    retrieval_query: str
    retrieved_chunks: list[dict]
    citations: list[dict]
    handoff_request: dict | None

def check_diagnosis_information(state: DiagnosisGraphState) -> dict:
    update = check_information_completeness(state)

    update["retrieval_query"] = ""
    update["retrieved_chunks"] = []
    update["citations"] = []
    update["handoff_request"] = None
    # 库存查询还需要零件号。
    if state["requested_tool"] == "lookup_inventory":
        part_number = state.get("part_number")

        if not isinstance(part_number, str) or not part_number.strip():
            missing_fields = [*update["missing_fields"], "part_number"]

            field_labels = {
                **FIELD_LABELS,
                "part_number": "零件号（part_number）",
            }
            labels = "、".join(
                field_labels[field] for field in missing_fields
            )

            update = {
                **update,
                "missing_fields": missing_fields,
                "next_action": "ask_clarifying_question",
                "clarifying_question": f"请补充以下诊断信息：{labels}。",
            }

    return update


def choose_next_node(
    state: DiagnosisGraphState,
) -> Literal["ask_clarifying_question", "route_selected_tool"]:
    if state["next_action"] == "ask_clarifying_question":
        return "ask_clarifying_question"
    return "route_selected_tool"


def ask_clarifying_question(state: DiagnosisGraphState) -> dict:
    return {
        "status": "needs_info",
        "stop_reason": None,
        "answer": state["clarifying_question"],
        "trace": [*state["trace"], "ask_clarifying_question"],
    }


def route_selected_tool(state: DiagnosisGraphState, *, dtc_lookup=None) -> dict:
    tool_call = build_tool_call(state["requested_tool"], state)

    # 复制列表，避免修改上一次执行返回的记录。
    run_state = {
        "tool_call_count": state["tool_call_count"],
        "max_tool_calls": state["max_tool_calls"],
        "seen_tool_calls": list(state["seen_tool_calls"]),
        "tool_trace": list(state["tool_trace"]),
    }

    try:
        tool_result = execute_guarded_tool_call(tool_call, run_state, dtc_lookup=dtc_lookup)
    except ToolCallRejected as error:
        tool_result = None
        status = "stopped"
        stop_reason = error.reason
        answer = str(error)
    except ToolExecutionFailed as error:
        tool_result = None
        status = "needs_human"
        stop_reason = error.reason
        answer = str(error)
    else:
        status = "running"
        stop_reason = None
        answer = ""

    return {
        "tool_call": tool_call,
        "tool_result": tool_result,
        "tool_call_count": run_state["tool_call_count"],
        "seen_tool_calls": run_state["seen_tool_calls"],
        "tool_trace": run_state["tool_trace"],
        "status": status,
        "stop_reason": stop_reason,
        "answer": answer,
        "next_action": "handoff_to_human" if status == "needs_human" else state["next_action"],
        "trace": [*state["trace"], "route_selected_tool"],
    }


def handoff_to_human(state: DiagnosisGraphState) -> dict:
    return {
        "answer": f'{state["answer"]}。已停止自动诊断，请人工复核后继续处理。',
        "handoff_request": {
            "reason": state["stop_reason"],
            "vehicle_id": state["vehicle_id"],
            "symptom": state["symptom"],
            "dtc_codes": list(state["dtc_codes"]),
            "failed_tool_call": deepcopy(state["tool_call"]),
            "error": deepcopy(state["tool_trace"][-1]),
            "tool_call_count": state["tool_call_count"],
        },
        "trace": [*state["trace"], "handoff_to_human"],
    }


def retrieve_knowledge(state: DiagnosisGraphState) -> dict:
    result = state["tool_result"]
    if result is None:
        raise RuntimeError("缺少 DTC 工具查询结果")

    dtc_code = result["dtc_code"].strip()
    query = f'{state["symptom"].strip()} {dtc_code}'

    # 完整词项匹配：忽略大小写，但不会把 P0AA60 当作 P0AA6。
    eligible_chunks = [
        chunk
        for chunk in state.get("knowledge_chunks", [])
        if dtc_code.lower() in tokenize(chunk["text"])
    ]

    # 先筛选符合条件的资料，再做 BM25 排序。
    candidates = search_knowledge(
        query,
        eligible_chunks,
        top_k=3,
    )

    return {
        "retrieval_query": query,
        "retrieved_chunks": candidates,
        "trace": [*state["trace"], "retrieve_knowledge"],
    }

def format_diagnosis(state: DiagnosisGraphState) -> dict:
    result = state["tool_result"]
    if result is None:
        raise RuntimeError("缺少工具查询结果")

    status = "ok"
    citations = []

    if "dtc_code" in result:
        candidates = state.get("retrieved_chunks", [])

        if not candidates:
            status = "no_evidence"
            answer = (
                f'故障码 {result["dtc_code"]} 查询已完成。'
                "资料库中没有匹配的候选资料，暂不生成诊断建议。"
            )
        else:
            citations = [
                {
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "source": item["source"],
                }
                for item in candidates
            ]

            # 展示原文，让引用对应实际检索到的片段。
            excerpts = [
                f'{item["text"]} [来源: {item["chunk_id"]}]'
                for item in candidates
            ]

            answer = (
                f'故障码 {result["dtc_code"]} 查询已完成。\n'
                "候选资料（相关性待核实）：\n"
                + "\n".join(excerpts)
            )

    elif "last_mileage_km" in result:
        recent_visits = result["recent_visits"]
        recent_summary = (
            recent_visits[0]["summary"]
            if recent_visits
            else "无历史到店记录"
        )
        answer = (
            f'车辆里程：{result["last_mileage_km"]} km。'
            f'最近记录：{recent_summary}。'
        )

    elif "part_number" in result:
        answer = (
            f'零件 {result["part_number"]}：{result["description"]}。'
            f'库存：{result["available_quantity"]}，'
            f'仓库：{result["warehouse"]}。'
        )

    else:
        raise RuntimeError("未知工具返回结构")

    return {
        "status": status,
        "stop_reason": None,
        "answer": answer,
        "citations": citations,
        "trace": [*state["trace"], "format_diagnosis"],
    }

def choose_after_tool(
    state: DiagnosisGraphState,
) -> Literal["finish", "handoff_to_human", "retrieve_knowledge", "format_diagnosis"]:
    if state["status"] == "stopped":
        return "finish"
    if state["status"] == "needs_human":
        return "handoff_to_human"

    if state["requested_tool"] == "lookup_dtc":
        return "retrieve_knowledge"

    return "format_diagnosis"

def build_diagnosis_graph(checkpointer=None, *, dtc_lookup=None):
    if dtc_lookup is not None and not callable(dtc_lookup):
        raise ValueError("dtc_lookup 必须是可调用的工具函数")
    builder = StateGraph(DiagnosisGraphState)

    builder.add_node(
        "check_diagnosis_information",
        check_diagnosis_information,
    )
    builder.add_node(
        "ask_clarifying_question",
        ask_clarifying_question,
    )
    builder.add_node("route_selected_tool", partial(route_selected_tool, dtc_lookup=dtc_lookup))
    builder.add_node("retrieve_knowledge", retrieve_knowledge)
    builder.add_node("format_diagnosis", format_diagnosis)
    builder.add_node("handoff_to_human", handoff_to_human)

    builder.add_edge(START, "check_diagnosis_information")

    builder.add_conditional_edges(
        "check_diagnosis_information",
        choose_next_node,
    )

    builder.add_edge("ask_clarifying_question", END)

    builder.add_conditional_edges(
        "route_selected_tool",
        choose_after_tool,
        {
            "finish": END,
            "handoff_to_human": "handoff_to_human",
            "retrieve_knowledge": "retrieve_knowledge",
            "format_diagnosis": "format_diagnosis",
        },
    )

    builder.add_edge("retrieve_knowledge", "format_diagnosis")
    builder.add_edge("format_diagnosis", END)
    builder.add_edge("handoff_to_human", END)

    return builder.compile(checkpointer=checkpointer)
