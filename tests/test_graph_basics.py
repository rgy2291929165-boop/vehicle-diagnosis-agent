"""第三周 Day 1：验证独立的无 LLM 三节点图。"""

from app import graph_basics


EXPECTED_TRACE = ["normalize_question", "lookup_mock", "format_result"]


def run_graph(question: str) -> dict:
    graph = graph_basics.build_graph()
    return graph.invoke(
        {
            "question": question,
            "query": "",
            "evidence": [],
            "answer": "",
            "trace": [],
        }
    )


def test_matching_question_uses_three_nodes_and_cites_mock_evidence():
    result = run_graph("绝缘故障应该先做什么？")

    assert result["trace"] == EXPECTED_TRACE
    assert len(result["evidence"]) == 1
    evidence = result["evidence"][0]
    assert evidence["chunk_id"]
    assert evidence["text"]
    assert evidence["chunk_id"] in result["answer"]


def test_question_is_preserved_while_query_is_normalized():
    question = "  绝缘故障应该先做什么？  "

    result = run_graph(question)

    assert result["question"] == question
    assert result["query"] == question.strip()
    assert result["trace"] == EXPECTED_TRACE


def test_unmatched_question_ends_without_inventing_repair_steps():
    result = run_graph("轮胎气压异常怎么办？")

    assert result["trace"] == EXPECTED_TRACE
    assert result["evidence"] == []
    assert "资料不足" in result["answer"]
    assert not any(step in result["answer"] for step in ("拆卸", "更换", "短接"))
