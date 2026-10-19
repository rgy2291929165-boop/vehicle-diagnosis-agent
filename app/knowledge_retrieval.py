"""使用 BM25 返回带来源的知识库候选片段。"""

from app.bm25 import BM25Retriever, tokenize


def search_knowledge(
    query: str,
    chunks: list[dict],
    top_k: int = 3,
) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query 必须是非空字符串")

    # bool 也是 int 的子类，因此这里使用 type 严格检查。
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k 必须是正整数")

    query = query.strip()

    if not chunks or not tokenize(query):
        return []

    if not any(tokenize(chunk["text"]) for chunk in chunks):
        return []

    retriever = BM25Retriever().fit(chunks)
    scores = retriever.score(query)

    ranked_ids = sorted(
        scores,
        key=lambda chunk_id: scores[chunk_id],
        reverse=True,
    )

    # 排除零分片段，再限制返回数量。
    matched_ids = [
        chunk_id
        for chunk_id in ranked_ids
        if scores[chunk_id] > 0
    ][:top_k]

    chunks_by_id = {
        chunk["chunk_id"]: chunk
        for chunk in chunks
    }

    # 创建新字典，保留正文和来源，不修改输入资料。
    return [
        {
            **chunks_by_id[chunk_id],
            "score": scores[chunk_id],
        }
        for chunk_id in matched_ids
    ]