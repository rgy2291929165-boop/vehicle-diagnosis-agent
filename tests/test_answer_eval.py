from app.answer_eval import (
    evaluate_answer,
    extract_cited_chunk_ids,
    order_contiguous_contexts,
)


def test_extract_cited_chunk_ids_preserves_order_and_removes_duplicates():
    assert extract_cited_chunk_ids(
        "结论。[来源: doc-a:0] 补充。[来源: doc-b:1] [来源: doc-a:0]"
    ) == ["doc-a:0", "doc-b:1"]


def test_extract_cited_chunk_ids_accepts_the_prompted_piece_id_label():
    assert extract_cited_chunk_ids("结论。[来源: 片段 ID: doc-a:0]") == ["doc-a:0"]


def test_answer_eval_distinguishes_document_citation_from_complete_evidence():
    result = evaluate_answer(
        question={
            "answerable": True,
            "gold_document_ids": ["doc-a"],
        },
        raw_answer="可设置预约。[来源: doc-a:1]",
        gold_chunk_ids={"doc-a:0"},
        retrieved_chunk_ids=["doc-a:1", "doc-a:0"],
    )

    assert result["actual_status"] == "ok"
    assert result["citation_correct"] is True
    assert result["citation_has_complete_evidence"] is False
    assert result["unsupported_claim"] is None
    assert result["format_valid"] is True


def test_answer_eval_requires_no_evidence_response_for_unanswerable_question():
    result = evaluate_answer(
        question={"answerable": False, "gold_document_ids": []},
        raw_answer="NO_EVIDENCE",
        gold_chunk_ids=set(),
        retrieved_chunk_ids=["doc-a:0"],
    )

    assert result["actual_status"] == "no_evidence"
    assert result["no_evidence_refusal_correct"] is True
    assert result["format_valid"] is True


def test_context_order_restores_source_order_only_for_adjacent_result_chunks():
    assert order_contiguous_contexts(
        ["doc-a:1", "doc-a:0", "doc-b:0", "doc-a:2"]
    ) == ["doc-a:0", "doc-a:1", "doc-b:0", "doc-a:2"]
