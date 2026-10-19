"""Deterministic checks around the manual Week 2 answer-quality review."""

import re
from typing import Dict, List, Sequence, Set


CITATION_PATTERN = re.compile(r"\[来源:\s*(?:片段\s*ID\s*:\s*)?([^\]]+?)\s*\]")


def extract_cited_chunk_ids(answer: str) -> List[str]:
    """Extract inline ``[来源: document_id:chunk_index]`` references in order."""
    return list(dict.fromkeys(CITATION_PATTERN.findall(answer)))


def chunk_document_id(chunk_id: str) -> str:
    document_id, separator, chunk_index = chunk_id.rpartition(":")
    if not separator or not document_id or not chunk_index.isdigit():
        raise ValueError(f"无效的片段 ID：{chunk_id}")
    return document_id


def order_contiguous_contexts(chunk_ids: Sequence[str]) -> List[str]:
    """Restore source order only inside contiguous same-document result groups.

    Retrieval relevance between documents remains unchanged.  Adjacent,
    overlapping chunks from one document are shown in source order so a model
    can cite the chunk containing a complete sentence instead of its fragment.
    """
    ordered = []
    index = 0
    while index < len(chunk_ids):
        document_id = chunk_document_id(chunk_ids[index])
        group = [chunk_ids[index]]
        index += 1
        while index < len(chunk_ids) and chunk_document_id(chunk_ids[index]) == document_id:
            group.append(chunk_ids[index])
            index += 1
        ordered.extend(sorted(group, key=lambda chunk_id: int(chunk_id.rsplit(":", 1)[1])))
    return ordered


def evaluate_answer(
    question: Dict,
    raw_answer: str,
    gold_chunk_ids: Set[str],
    retrieved_chunk_ids: Sequence[str],
) -> Dict:
    """Score provenance mechanically and leave semantic claims for human review."""
    normalized_answer = raw_answer.strip()
    actual_status = "no_evidence" if normalized_answer == "NO_EVIDENCE" else "ok"
    cited_chunk_ids = extract_cited_chunk_ids(normalized_answer)

    result = {
        "expected_status": "ok" if question["answerable"] else "no_evidence",
        "actual_status": actual_status,
        "cited_chunk_ids": cited_chunk_ids,
        "retrieved_chunk_ids": list(retrieved_chunk_ids),
        "unsupported_claim": None,
        "manual_review_required": True,
        "manual_review_note": None,
    }

    if question["answerable"]:
        gold_document_ids = set(question["gold_document_ids"])
        cited_document_ids = {
            chunk_document_id(chunk_id) for chunk_id in cited_chunk_ids
        }
        result.update(
            {
                "citation_correct": bool(cited_document_ids & gold_document_ids),
                "citation_has_complete_evidence": bool(
                    set(cited_chunk_ids) & gold_chunk_ids
                ),
                "no_evidence_refusal_correct": None,
                "format_valid": actual_status == "ok" and bool(cited_chunk_ids),
            }
        )
    else:
        result.update(
            {
                "citation_correct": None,
                "citation_has_complete_evidence": None,
                "no_evidence_refusal_correct": actual_status == "no_evidence",
                "format_valid": actual_status == "no_evidence" and not cited_chunk_ids,
            }
        )
    return result
