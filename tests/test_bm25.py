from app.bm25 import BM25Retriever, tokenize


def test_tokenize_keeps_chinese_characters_and_alphanumeric_terms():
    assert tokenize("电池 BMS_a053 16A") == ["电", "池", "bms_a053", "16a"]


def test_bm25_ranks_chunk_with_more_matching_terms_first():
    retriever = BM25Retriever().fit(
        [
            {"chunk_id": "battery", "text": "高压电池 充电 电池"},
            {"chunk_id": "door", "text": "充电口 门 锁扣"},
        ]
    )

    assert retriever.rank("高压电池充电")[0] == "battery"


def test_bm25_rejects_invalid_hyperparameters():
    try:
        BM25Retriever(k1=0)
    except ValueError as error:
        assert "k1" in str(error)
    else:
        raise AssertionError("k1=0 应被拒绝")
