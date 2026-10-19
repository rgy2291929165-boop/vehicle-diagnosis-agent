"""Pure metric helpers for the reproducible Week 2 retrieval evaluation."""

from typing import Dict, Iterable, List, Mapping, Sequence, Set


DEFAULT_KS = (1, 3, 5)


def find_gold_chunk_ids(
    questions: Iterable[Dict], chunks: Iterable[Dict]
) -> Dict[str, Set[str]]:
    """Map each answerable question to chunks containing its annotated evidence."""
    chunk_list = list(chunks)
    gold_by_question: Dict[str, Set[str]] = {}

    for question in questions:
        if not question["answerable"]:
            gold_by_question[question["id"]] = set()
            continue

        gold_chunks: Set[str] = set()
        for document_id, quote in zip(
            question["gold_document_ids"], question["gold_evidence_quotes"]
        ):
            matched_chunks = {
                chunk["chunk_id"]
                for chunk in chunk_list
                if chunk["document_id"] == document_id and quote in chunk["text"]
            }
            if not matched_chunks:
                raise ValueError(
                    f"{question['id']} 的证据未出现在任何评测片段中: {document_id}"
                )
            gold_chunks.update(matched_chunks)

        gold_by_question[question["id"]] = gold_chunks

    return gold_by_question


def first_relevant_rank(ranked_chunk_ids: Sequence[str], gold_chunk_ids: Set[str]):
    for position, chunk_id in enumerate(ranked_chunk_ids, start=1):
        if chunk_id in gold_chunk_ids:
            return position
    return None


def chunk_document_id(chunk_id: str) -> str:
    """Return the document ID from the project's ``document_id:chunk_index`` ID."""
    document_id, separator, chunk_index = chunk_id.rpartition(":")
    if not separator or not document_id or not chunk_index.isdigit():
        raise ValueError(f"无效的评测片段 ID：{chunk_id}")
    return document_id


def first_relevant_document_rank(
    ranked_chunk_ids: Sequence[str], gold_document_ids: Set[str]
):
    """Return the first rank whose chunk belongs to a gold document."""
    for position, chunk_id in enumerate(ranked_chunk_ids, start=1):
        if chunk_document_id(chunk_id) in gold_document_ids:
            return position
    return None


def evaluate_rankings(
    questions: Iterable[Dict],
    rankings: Mapping[str, Sequence[str]],
    gold_by_question: Mapping[str, Set[str]],
    ks: Sequence[int] = DEFAULT_KS,
) -> Dict:
    """Compute evidence-chunk Recall@K and MRR without scoring no-evidence items."""
    positive_results: List[Dict] = []
    no_evidence_results: List[Dict] = []

    for question in questions:
        question_id = question["id"]
        ranked_chunk_ids = list(rankings[question_id])

        if not question["answerable"]:
            no_evidence_results.append(
                {
                    "id": question_id,
                    "ranked_chunk_ids": ranked_chunk_ids,
                    "returned_candidates": bool(ranked_chunk_ids),
                    "candidate_count": len(ranked_chunk_ids),
                }
            )
            continue

        rank = first_relevant_rank(ranked_chunk_ids, gold_by_question[question_id])
        document_rank = first_relevant_document_rank(
            ranked_chunk_ids, set(question["gold_document_ids"])
        )
        positive_results.append(
            {
                "id": question_id,
                "gold_chunk_ids": sorted(gold_by_question[question_id]),
                "gold_document_ids": sorted(question["gold_document_ids"]),
                "ranked_chunk_ids": ranked_chunk_ids,
                "first_relevant_rank": rank,
                "first_relevant_document_rank": document_rank,
                "reciprocal_rank": 0.0 if rank is None else 1.0 / rank,
                "hits": {
                    f"recall_at_{k}": rank is not None and rank <= k for k in ks
                },
                "document_hits": {
                    f"document_recall_at_{k}": document_rank is not None
                    and document_rank <= k
                    for k in ks
                },
            }
        )

    if not positive_results:
        raise ValueError("评测集没有可回答题，无法计算检索指标")

    count = len(positive_results)
    retrieval_metrics = {
        f"recall_at_{k}": sum(
            result["hits"][f"recall_at_{k}"] for result in positive_results
        )
        / count
        for k in ks
    }
    retrieval_metrics["mrr"] = sum(
        result["reciprocal_rank"] for result in positive_results
    ) / count
    document_metrics = {
        f"document_recall_at_{k}": sum(
            result["document_hits"][f"document_recall_at_{k}"]
            for result in positive_results
        )
        / count
        for k in ks
    }

    return {
        "metrics": retrieval_metrics,
        "document_metrics": document_metrics,
        "answerable_count": count,
        "no_evidence_count": len(no_evidence_results),
        "no_evidence_candidate_rate": sum(
            result["returned_candidates"] for result in no_evidence_results
        )
        / len(no_evidence_results)
        if no_evidence_results
        else None,
        "positive_results": positive_results,
        "no_evidence_results": no_evidence_results,
    }
