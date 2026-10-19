"""Rank-based fusion utilities for the Week 2 hybrid-retrieval exercise."""

import math
from typing import List, Mapping, Sequence


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> List[str]:
    """Fuse named rankings with RRF and return a deterministic chunk ranking.

    RRF uses only rank positions, so vector similarities and BM25 scores do not
    need to be calibrated to the same numeric range.  When fused scores tie,
    the chunk first encountered in the input rankings wins deterministically.
    """
    if not rankings:
        raise ValueError("至少需要一份待融合的排序结果")
    if k < 0:
        raise ValueError("RRF 的 k 不能小于 0")

    if weights is None:
        weights = {name: 1.0 for name in rankings}
    if set(weights) != set(rankings):
        raise ValueError("权重必须与每份排序结果一一对应")

    scores = {}
    first_seen = {}
    for name, ranked_chunk_ids in rankings.items():
        weight = weights[name]
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"{name} 的权重必须是非负有限数")
        if len(ranked_chunk_ids) != len(set(ranked_chunk_ids)):
            raise ValueError(f"{name} 的排序结果包含重复片段 ID")

        for rank, chunk_id in enumerate(ranked_chunk_ids, start=1):
            first_seen.setdefault(chunk_id, len(first_seen))
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)

    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id]))
