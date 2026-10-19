"""A small, dependency-free BM25 retriever for the Week 2 benchmark."""

import math
import re
from collections import Counter
from typing import Dict, Iterable, List


TOKENIZER_NAME = "zh_character_plus_alnum"
TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    """Split Chinese into characters and preserve contiguous Latin/digit tokens."""
    return TOKEN_PATTERN.findall(text.lower())


class BM25Retriever:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        if k1 <= 0:
            raise ValueError("k1 必须大于 0")
        if not 0 <= b <= 1:
            raise ValueError("b 必须在 0 到 1 之间")
        self.k1 = k1
        self.b = b
        self._chunk_ids: List[str] = []
        self._term_frequencies: List[Counter] = []
        self._document_frequencies: Counter = Counter()
        self._document_lengths: List[int] = []
        self._average_document_length = 0.0

    def fit(self, chunks: Iterable[Dict]) -> "BM25Retriever":
        chunk_list = list(chunks)
        if not chunk_list:
            raise ValueError("不能为 BM25 建立空索引")

        chunk_ids = [chunk["chunk_id"] for chunk in chunk_list]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("BM25 片段 ID 必须唯一")

        self._chunk_ids = chunk_ids
        self._term_frequencies = [Counter(tokenize(chunk["text"])) for chunk in chunk_list]
        self._document_lengths = [sum(counts.values()) for counts in self._term_frequencies]
        self._average_document_length = sum(self._document_lengths) / len(
            self._document_lengths
        )
        self._document_frequencies = Counter()
        for counts in self._term_frequencies:
            self._document_frequencies.update(counts.keys())
        return self

    def _idf(self, token: str) -> float:
        document_count = len(self._chunk_ids)
        frequency = self._document_frequencies[token]
        return math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))

    def score(self, query: str) -> Dict[str, float]:
        if not self._chunk_ids:
            raise RuntimeError("请先调用 fit()")

        query_tokens = set(tokenize(query))
        scores = {}
        for chunk_id, term_frequencies, document_length in zip(
            self._chunk_ids, self._term_frequencies, self._document_lengths
        ):
            length_normalizer = self.k1 * (
                1 - self.b + self.b * document_length / self._average_document_length
            )
            score = 0.0
            for token in query_tokens:
                term_frequency = term_frequencies[token]
                if not term_frequency:
                    continue
                score += self._idf(token) * term_frequency * (self.k1 + 1) / (
                    term_frequency + length_normalizer
                )
            scores[chunk_id] = score
        return scores

    def rank(self, query: str) -> List[str]:
        scores = self.score(query)
        order_by_id = {chunk_id: index for index, chunk_id in enumerate(self._chunk_ids)}
        return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], order_by_id[chunk_id]))
