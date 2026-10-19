from app.llm import ANSWER_PROMPT_VERSION, build_messages


def test_week2_prompt_prefers_supported_answer_and_uses_parseable_citations():
    messages = build_messages(
        "充电口锁扣冻结怎么办？",
        [
            {
                "source": "official",
                "chunk_id": "doc-a:0",
                "text": "可使用加热功能。",
            }
        ],
    )

    system_prompt = messages[0]["content"]
    assert ANSWER_PROMPT_VERSION == "week2-answer-v4"
    assert "应给出简洁回答" in system_prompt
    assert "只回答问题直接要求的结论" in system_prompt
    assert "[来源: document_id:chunk_index]" in system_prompt
    assert "包含完整句子和完整设置名称" in system_prompt
    assert "仅当所有资料片段都不能直接支持" in system_prompt
