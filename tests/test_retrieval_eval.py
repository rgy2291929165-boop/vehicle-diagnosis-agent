from app.retrieval_eval import evaluate_rankings, find_gold_chunk_ids


def test_find_gold_chunk_ids_requires_annotated_evidence_in_a_chunk():
    questions = [
        {
            "id": "Q1",
            "answerable": True,
            "gold_document_ids": ["doc-a"],
            "gold_evidence_quotes": ["唯一证据"],
        }
    ]
    chunks = [
        {"chunk_id": "doc-a:0", "document_id": "doc-a", "text": "这里有唯一证据。"}
    ]

    assert find_gold_chunk_ids(questions, chunks) == {"Q1": {"doc-a:0"}}


def test_evaluate_rankings_excludes_no_evidence_questions_from_recall_and_mrr():
    questions = [
        {"id": "Q1", "answerable": True, "gold_document_ids": ["doc-a"]},
        {"id": "Q2", "answerable": True, "gold_document_ids": ["doc-b"]},
        {"id": "Q3", "answerable": False},
    ]
    report = evaluate_rankings(
        questions,
        rankings={
            "Q1": ["doc-a:0", "doc-b:0"],
            "Q2": ["doc-a:0", "doc-b:0", "doc-c:0"],
            "Q3": ["doc-a:0"],
        },
        gold_by_question={"Q1": {"doc-a:0"}, "Q2": {"doc-b:0"}, "Q3": set()},
    )

    assert report["metrics"] == {
        "recall_at_1": 0.5,
        "recall_at_3": 1.0,
        "recall_at_5": 1.0,
        "mrr": 0.75,
    }
    assert report["no_evidence_candidate_rate"] == 1.0
    assert report["no_evidence_results"][0]["ranked_chunk_ids"] == ["doc-a:0"]


def test_evaluate_rankings_distinguishes_document_hits_from_complete_evidence_hits():
    report = evaluate_rankings(
        questions=[
            {
                "id": "Q1",
                "answerable": True,
                "gold_document_ids": ["doc-a"],
            }
        ],
        rankings={"Q1": ["doc-a:1", "doc-a:0"]},
        gold_by_question={"Q1": {"doc-a:0"}},
    )

    assert report["metrics"]["recall_at_1"] == 0.0
    assert report["document_metrics"]["document_recall_at_1"] == 1.0
    result = report["positive_results"][0]
    assert result["first_relevant_rank"] == 2
    assert result["first_relevant_document_rank"] == 1
