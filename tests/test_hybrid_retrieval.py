import pytest

from app.hybrid_retrieval import reciprocal_rank_fusion


def test_rrf_promotes_a_chunk_ranked_highly_by_both_retrievers():
    ranking = reciprocal_rank_fusion(
        {
            "vector": ["vector_only", "shared"],
            "bm25": ["shared", "bm25_only"],
        }
    )

    assert ranking == ["shared", "vector_only", "bm25_only"]


def test_rrf_keeps_chunks_returned_by_only_one_retriever():
    ranking = reciprocal_rank_fusion(
        {"vector": ["semantic"], "bm25": ["lexical"]}
    )

    assert ranking == ["semantic", "lexical"]


def test_rrf_breaks_equal_scores_by_first_seen_input_order():
    ranking = reciprocal_rank_fusion(
        {"vector": ["first", "second"], "bm25": ["second", "first"]}
    )

    assert ranking == ["first", "second"]


def test_rrf_rejects_duplicate_chunk_ids_in_one_ranking():
    with pytest.raises(ValueError, match="重复片段 ID"):
        reciprocal_rank_fusion({"vector": ["same", "same"], "bm25": []})
