"""第三周 Day 1：不依赖 LLM 的三节点 LangGraph 练习。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class Evidence(TypedDict):
    """模拟检索返回的一条可追溯证据。"""

    chunk_id: str
    text: str


class DiagnosisState(TypedDict):
    """在图中依次被三个节点补全的最小诊断状态。"""

    question: str
    query: str
    evidence: list[Evidence]
    answer: str
    trace: Annotated[list[str], operator.add]


MOCK_INSULATION_EVIDENCE: Evidence = {
    "chunk_id": "mock-insulation-guide:0",
    "text": "绝缘故障应先读取故障码，并按资料确认后续检查范围。",
}


def normalize_question(state: DiagnosisState) -> dict:
    """保留原问题，生成用于后续查询的去首尾空白版本。"""

    return {
        "query": state["question"].strip(),
        "trace": ["normalize_question"],
    }


def lookup_mock(state: DiagnosisState) -> dict:
    """按规范化问题从内存中的固定示例查找证据。"""

    evidence = [MOCK_INSULATION_EVIDENCE] if "绝缘" in state["query"] else []
    return {
        "evidence": evidence,
        "trace": ["lookup_mock"],
    }


def format_result(state: DiagnosisState) -> dict:
    """仅根据模拟证据生成固定答复。"""

    if not state["evidence"]:
        answer = "资料不足，无法提供具体维修步骤。"
    else:
        evidence = state["evidence"][0]
        answer = f'{evidence["text"]} [证据: {evidence["chunk_id"]}]'

    return {
        "answer": answer,
        "trace": ["format_result"],
    }


def build_graph():
    """构建并编译固定的 START → 三节点 → END 路径。"""

    builder = StateGraph(DiagnosisState)
    builder.add_node("normalize_question", normalize_question)
    builder.add_node("lookup_mock", lookup_mock)
    builder.add_node("format_result", format_result)
    builder.add_edge(START, "normalize_question")
    builder.add_edge("normalize_question", "lookup_mock")
    builder.add_edge("lookup_mock", "format_result")
    builder.add_edge("format_result", END)
    return builder.compile()
