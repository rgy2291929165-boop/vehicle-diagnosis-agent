"""共享的纯文本切片规则，不导入向量库或模型。"""

from typing import List

CHUNK_SIZE = 200
CHUNK_OVERLAP = 40


def split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    clean_text = " ".join(text.split())

    if not clean_text:
        return []

    chunks = []
    start = 0

    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))
        chunks.append(clean_text[start:end])

        if end == len(clean_text):
            break

        start = end - overlap

    return chunks
