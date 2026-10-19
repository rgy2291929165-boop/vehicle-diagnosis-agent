from copy import deepcopy

import pytest

from app.knowledge_retrieval import search_knowledge


def make_chunks():
    # 测试资料只用于验证检索行为。
    return [
        {
            "chunk_id": "demo:0",
            "document_id": "demo",
            "text": "P0AA6 绝缘 故障 检查",
            "source": "tests/demo.txt",
        },
        {
            "chunk_id": "demo:1",
            "document_id": "demo",
            "text": "绝缘 故障",
            "source": "tests/demo.txt",
        },
        {
            "chunk_id": "door:0",
            "document_id": "door",
            "text": "车门 锁扣",
            "source": "tests/door.txt",
        },
    ]


def test_search_ranks_matches_and_preserves_sources():
    results = search_knowledge("P0AA6 绝缘", make_chunks())

    assert [item["chunk_id"] for item in results] == [
        "demo:0",
        "demo:1",
    ]
    assert results[0]["document_id"] == "demo"
    assert results[0]["source"] == "tests/demo.txt"
    assert results[0]["text"] == "P0AA6 绝缘 故障 检查"
    assert results[0]["score"] > results[1]["score"] > 0


def test_search_respects_top_k():
    results = search_knowledge(
        "P0AA6 绝缘", make_chunks(), top_k=1
    )

    assert len(results) == 1
    assert results[0]["chunk_id"] == "demo:0"


def test_search_returns_empty_when_no_terms_match():
    results = search_knowledge("XYZ_UNSEEN_999", make_chunks())

    assert results == []


def test_search_returns_empty_for_empty_corpus():
    assert search_knowledge("P0AA6", []) == []


@pytest.mark.parametrize("query", ["", "   ", None])
def test_search_rejects_invalid_query(query):
    with pytest.raises(ValueError, match="query"):
        search_knowledge(query, make_chunks())


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_search_rejects_invalid_top_k(top_k):
    with pytest.raises(ValueError, match="top_k"):
        search_knowledge("P0AA6", make_chunks(), top_k=top_k)


def test_search_does_not_modify_input_chunks():
    chunks = make_chunks()
    original = deepcopy(chunks)

    results = search_knowledge("P0AA6", chunks)

    assert chunks == original

    # 修改返回的片段也不能修改原始资料。
    results[0]["text"] = "修改后的候选文本"
    assert chunks == original