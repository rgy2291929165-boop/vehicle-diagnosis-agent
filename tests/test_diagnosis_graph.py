import pytest

from app import diagnosis_graph, tool_router
from app.diagnosis_graph import build_diagnosis_graph
from copy import deepcopy

def run_graph(**overrides):
    state = {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
        "part_number": "HV-ISO-SENSOR-01",
        "requested_tool": "lookup_dtc",
        "missing_fields": [],
        "next_action": "ask_clarifying_question",
        "clarifying_question": None,
        "tool_call": None,
        "tool_result": None,
        "tool_trace": [],
        "answer": "",
        "trace": [],
        "tool_call_count": 0,
        "max_tool_calls": 2,
        "seen_tool_calls": [],
        "status": "running",
        "stop_reason": None,
        "knowledge_chunks": [],
        "retrieval_query": "",
        "retrieved_chunks": [],
        "citations": [],
    }
    state.update(overrides)
    return build_diagnosis_graph().invoke(state)


def test_incomplete_information_ends_with_a_clarifying_question():
    result = run_graph(dtc_codes=[])

    assert result["next_action"] == "ask_clarifying_question"
    assert "故障码（DTC）" in result["clarifying_question"]
    assert result["tool_call"] is None
    assert result["tool_result"] is None
    assert result["tool_trace"] == []
    assert result["trace"] == [
        "check_information_completeness",
        "ask_clarifying_question",
    ]


def test_complete_information_uses_planned_dtc_call_and_keeps_a_trace():
    result = run_graph()

    assert result["next_action"] == "route_tools"
    assert result["tool_call"] == {
        "tool_name": "lookup_dtc",
        "arguments": {
            "vehicle_id": "VIN-DEMO-001",
            "dtc_code": "P0AA6",
        },
    }
    assert result["tool_result"]["dtc_code"] == "P0AA6"
    assert result["tool_trace"] == [
        {
            "tool_name": "lookup_dtc",
            "status": "success",
        }
    ]
    assert "P0AA6" in result["answer"]
    assert result["trace"] == [
        "check_information_completeness",
        "route_selected_tool",
        "retrieve_knowledge",
        "format_diagnosis",
    ]


def test_complete_information_can_use_the_planned_vehicle_history_tool():
    result = run_graph(requested_tool="lookup_vehicle_history")

    assert result["tool_call"] == {
        "tool_name": "lookup_vehicle_history",
        "arguments": {
            "vehicle_id": "VIN-DEMO-001",
        },
    }
    assert result["tool_result"]["last_mileage_km"] == 42350
    assert result["tool_trace"] == [
        {
            "tool_name": "lookup_vehicle_history",
            "status": "success",
        }
    ]

def test_graph_can_lookup_inventory():
    result = run_graph(requested_tool="lookup_inventory")

    assert result["tool_call"] == {
        "tool_name": "lookup_inventory",
        "arguments": {"part_number": "HV-ISO-SENSOR-01"},
    }
    assert result["tool_result"]["available_quantity"] == 2
    assert "HV-ISO-SENSOR-01" in result["answer"]


def test_missing_part_number_asks_before_inventory_lookup():
    result = run_graph(
        requested_tool="lookup_inventory",
        part_number="   ",
    )

    assert result["missing_fields"] == ["part_number"]
    assert result["next_action"] == "ask_clarifying_question"
    assert "零件号" in result["clarifying_question"]
    assert result["tool_call"] is None
    assert result["tool_result"] is None
    assert result["tool_trace"] == []

TOOLS = [
    "lookup_dtc",
    "lookup_vehicle_history",
    "lookup_inventory",
]




@pytest.mark.parametrize("requested_tool", TOOLS)
def test_graph_returns_stop_state_when_budget_is_exhausted(
    monkeypatch, requested_tool
):
    entered = []

    def fake_tool(**arguments):
        entered.append(arguments)
        return {}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        requested_tool,
        fake_tool,
    )

    result = run_graph(
        requested_tool=requested_tool,
        tool_call_count=2,
    )

    assert entered == []
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "tool_call_limit"
    assert result["tool_call_count"] == 2
    assert result["tool_result"] is None
    assert "调用次数" in result["answer"]
    assert "format_diagnosis" not in result["trace"]
    assert "retrieve_knowledge" not in result["trace"]
    assert result["tool_trace"] == [
        {
            "tool_name": requested_tool,
            "status": "rejected",
            "reason": "tool_call_limit",
        }
    ]


@pytest.mark.parametrize("requested_tool", TOOLS)
def test_graph_returns_stop_state_for_a_repeated_call(
    monkeypatch, requested_tool
):
    first_result = run_graph(requested_tool=requested_tool)
    entered = []

    def fake_tool(**arguments):
        entered.append(arguments)
        return {}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        requested_tool,
        fake_tool,
    )

    result = run_graph(
        requested_tool=requested_tool,
        tool_call_count=first_result["tool_call_count"],
        seen_tool_calls=first_result["seen_tool_calls"],
        tool_trace=first_result["tool_trace"],
    )

    assert entered == []
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "duplicate_tool_call"
    assert result["tool_call_count"] == 1
    assert result["tool_result"] is None
    assert "重复调用" in result["answer"]
    assert "format_diagnosis" not in result["trace"]
    assert "retrieve_knowledge" not in result["trace"]
    assert len(result["tool_trace"]) == 2
    assert result["tool_trace"][-1] == {
        "tool_name": requested_tool,
        "status": "rejected",
        "reason": "duplicate_tool_call",
    }

    # 新一次执行不能修改之前已经返回的记录。
    assert len(first_result["tool_trace"]) == 1

@pytest.mark.parametrize("requested_tool", TOOLS)
def test_graph_propagates_unexpected_tool_errors(
    monkeypatch, requested_tool
):
    entered = []

    def broken_tool(**arguments):
        entered.append(arguments)
        raise RuntimeError("模拟工具内部故障")

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        requested_tool,
        broken_tool,
    )

    with pytest.raises(RuntimeError, match="模拟工具内部故障"):
        run_graph(requested_tool=requested_tool)

    # 确认错误来自实际执行的工具。
    assert len(entered) == 1

def test_dtc_graph_retrieves_candidates_and_preserves_sources():
    chunks = [
        {
            "chunk_id": "demo:0",
            "document_id": "demo",
            "text": "P0AA6 绝缘 故障 检查",
            "source": "tests/demo.txt",
        },
    ]

    result = run_graph(knowledge_chunks=chunks)

    assert result["retrieval_query"] == "仪表提示绝缘故障 P0AA6"
    assert len(result["retrieved_chunks"]) == 1

    candidate = result["retrieved_chunks"][0]
    assert candidate["chunk_id"] == "demo:0"
    assert candidate["text"] == chunks[0]["text"]
    assert candidate["source"] == "tests/demo.txt"
    assert candidate["score"] > 0

    assert result["tool_call_count"] == 1
    assert result["trace"] == [
        "check_information_completeness",
        "route_selected_tool",
        "retrieve_knowledge",
        "format_diagnosis",
    ]

    # 检索不能给原始资料添加分数。
    assert "score" not in chunks[0]


def test_dtc_graph_keeps_an_empty_candidate_list_when_no_terms_match():
    result = run_graph(
        knowledge_chunks=[
            {
                "chunk_id": "door:0",
                "document_id": "door",
                "text": "车门 锁扣",
                "source": "tests/door.txt",
            },
        ],
    )

    assert result["retrieval_query"] == "仪表提示绝缘故障 P0AA6"
    assert result["retrieved_chunks"] == []
    assert "retrieve_knowledge" in result["trace"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"dtc_codes": []},
        {"tool_call_count": 2},
    ],
    ids=["needs_info", "budget_exhausted"],
)
def test_graph_skips_retrieval_and_clears_old_candidates(
    monkeypatch, overrides
):
    def forbidden_search(*args, **kwargs):
        pytest.fail("补问或预算耗尽时不应执行检索")

    # 当前尚未导入此函数，允许先安装测试替身。
    monkeypatch.setattr(
        diagnosis_graph,
        "search_knowledge",
        forbidden_search,
        raising=False,
    )

    result = run_graph(
        **overrides,
        retrieval_query="上一次查询",
        retrieved_chunks=[
            {
                "chunk_id": "old:0",
                "text": "上一次候选资料",
            },
        ],
    )

    assert "retrieve_knowledge" not in result["trace"]
    assert result["retrieval_query"] == ""
    assert result["retrieved_chunks"] == []

def test_dtc_answer_shows_candidate_text_and_its_source(monkeypatch):
    unsupported_advice = "测试用的无资料支持建议"

    def fake_dtc_tool(vehicle_id, dtc_code):
        return {
            "dtc_code": dtc_code,
            "description": "模拟故障码说明",
            "severity": "high",
            "recommended_check": unsupported_advice,
        }

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        "lookup_dtc",
        fake_dtc_tool,
    )

    text = "P0AA6 绝缘 故障 检查"
    result = run_graph(
        knowledge_chunks=[
            {
                "chunk_id": "demo:0",
                "document_id": "demo",
                "text": text,
                "source": "tests/demo.txt",
            },
        ],
    )

    assert result["status"] == "ok"
    assert "候选资料" in result["answer"]
    assert text in result["answer"]
    assert "[来源: demo:0]" in result["answer"]
    assert result["citations"] == [
        {
            "chunk_id": "demo:0",
            "document_id": "demo",
            "source": "tests/demo.txt",
        },
    ]

    # 工具自带的建议不能自动成为有资料支持的诊断建议。
    assert unsupported_advice not in result["answer"]


def test_dtc_answer_returns_no_evidence_without_candidates():
    result = run_graph(knowledge_chunks=[])

    assert result["status"] == "no_evidence"
    assert result["citations"] == []
    assert "P0AA6" in result["answer"]
    assert "没有匹配的候选资料" in result["answer"]

    advice = result["tool_result"]["recommended_check"]
    assert advice not in result["answer"]

    # 查询已经执行，不能因为没有资料而抹掉执行记录。
    assert result["tool_call_count"] == 1
    assert result["tool_trace"][-1]["status"] == "success"


@pytest.mark.parametrize(
    "overrides",
    [
        {"dtc_codes": []},
        {"tool_call_count": 2},
        {"requested_tool": "lookup_vehicle_history"},
        {"requested_tool": "lookup_inventory"},
    ],
    ids=["needs_info", "stopped", "history", "inventory"],
)
def test_graph_clears_old_citations_when_not_producing_dtc_candidates(
    overrides,
):
    result = run_graph(
        **overrides,
        citations=[
            {
                "chunk_id": "old:0",
                "document_id": "old",
                "source": "tests/old.txt",
            },
        ],
    )

    assert result["citations"] == []
    assert "[来源: old:0]" not in result["answer"]

@pytest.mark.parametrize(
    "text",
    [
        "绝缘故障需要查看仪表提示。",
        "P0AA60 绝缘故障检查",
    ],
    ids=["no_dtc", "different_dtc"],
)
def test_dtc_graph_rejects_candidates_without_the_selected_code(text):
    result = run_graph(
        knowledge_chunks=[
            {
                "chunk_id": "demo:0",
                "document_id": "demo",
                "text": text,
                "source": "tests/demo.txt",
            },
        ],
    )

    assert result["retrieved_chunks"]   == []

@pytest.mark.parametrize(
    "text",
    [
        "绝缘故障需要查看仪表提示。",
        "P0AA60 绝缘故障检查",
    ],
    ids=["no_dtc_code", "different_dtc_code"],
)
def test_dtc_graph_rejects_candidates_without_the_exact_code(text):
    result = run_graph(
        knowledge_chunks=[
            {
                "chunk_id": "demo:0",
                "document_id": "demo",
                "text": text,
                "source": "tests/demo.txt",
            },
        ],
    )

    assert result["status"] == "no_evidence"
    assert result["retrieved_chunks"] == []
    assert result["citations"] == []


def test_dtc_graph_matches_code_without_case_sensitivity():
    text = "p0aa6 绝缘故障检查"

    result = run_graph(
        knowledge_chunks=[
            {
                "chunk_id": "demo:0",
                "document_id": "demo",
                "text": text,
                "source": "tests/demo.txt",
            },
        ],
    )

    assert result["status"] == "ok"
    assert len(result["retrieved_chunks"]) == 1
    assert text in result["answer"]
    assert result["citations"][0]["chunk_id"] == "demo:0"


def make_turn_chunks():
    return [{
        "chunk_id": "turns:0",
        "document_id": "turns",
        "text": "P0AA6 多轮教学片段，仅用于验证状态传递。",
        "source": "demo/fixture",
    }]


def test_graph_continues_after_clarification_without_mutating_first_result():
    first = run_graph(
        dtc_codes=[],
        knowledge_chunks=make_turn_chunks(),
    )
    first_before = deepcopy(first)

    graph = build_diagnosis_graph()
    second = graph.invoke({
        **first,
        "dtc_codes": ["P0AA6"],
    })

    assert first["status"] == "needs_info"
    assert first["tool_call_count"] == 0
    assert second["status"] == "ok"
    assert second["tool_call_count"] == 1
    assert second["missing_fields"] == []
    assert second["clarifying_question"] is None
    assert len(second["citations"]) == 1
    assert second["trace"] == [
        *first_before["trace"],
        "check_information_completeness",
        "route_selected_tool",
        "retrieve_knowledge",
        "format_diagnosis",
    ]
    assert first == first_before


def test_graph_rejects_third_round_without_mutating_second_result():
    first = run_graph(
        dtc_codes=[],
        knowledge_chunks=make_turn_chunks(),
    )
    graph = build_diagnosis_graph()
    second = graph.invoke({**first, "dtc_codes": ["P0AA6"]})
    second_before = deepcopy(second)

    third = graph.invoke({**second})

    assert third["status"] == "stopped"
    assert third["stop_reason"] == "duplicate_tool_call"
    assert third["tool_call_count"] == 1
    assert third["citations"] == []
    assert third["retrieved_chunks"] == []
    assert third["tool_result"] is None
    assert third["seen_tool_calls"] == second_before["seen_tool_calls"]
    assert third["tool_trace"] == [
        *second_before["tool_trace"],
        {
            "tool_name": "lookup_dtc",
            "status": "rejected",
            "reason": "duplicate_tool_call",
        },
    ]

    # 完整路径保留历史；第三轮只新增检查和工具路由。
    assert third["trace"] == [
        *second_before["trace"],
        "check_information_completeness",
        "route_selected_tool",
    ]
    assert second == second_before