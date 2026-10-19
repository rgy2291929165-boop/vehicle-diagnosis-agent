from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.llm import ModelEmptyResponseError, ModelTimeoutError
from app.retrieval import split_text

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolate_document_imports(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DOCUMENTS_DIR", tmp_path)


def sample_evidence():
    return [
        {
            "chunk_id": "demo-document:0",
            "document_id": "demo-document",
            "title": "测试资料",
            "source": "tests/demo.txt",
            "source_type": "test",
            "chunk_index": 0,
            "text": "绝缘故障应先读取故障码。",
            "distance": 0.2,
        }
    ]


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_citations(monkeypatch):
    monkeypatch.setattr(main, "search_documents", lambda query, top_k: sample_evidence())
    monkeypatch.setattr(
        main,
        "generate_answer",
        lambda question, contexts: "应先读取故障码。[来源: demo-document:0]",
    )

    response = client.post(
        "/chat",
        json={"question": "绝缘故障应该先做什么？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "读取故障码" in body["answer"]
    assert body["citations"][0]["chunk_id"] == "demo-document:0"


def test_chat_returns_no_evidence(monkeypatch):
    monkeypatch.setattr(main, "search_documents", lambda query, top_k: [])

    response = client.post(
        "/chat",
        json={"question": "轮胎胎压异常怎么处理？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_evidence"
    assert body["citations"] == []
    assert "没有足够证据" in body["answer"]

def test_chat_maps_model_no_evidence(monkeypatch):
    monkeypatch.setattr(
        main,
        "search_documents",
        lambda query, top_k: sample_evidence(),
    )
    monkeypatch.setattr(
        main,
        "generate_answer",
        lambda question, contexts: "NO_EVIDENCE",
    )

    response = client.post(
        "/chat",
        json={"question": "座椅加热失效应该如何维修？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_evidence"
    assert body["citations"] == []

def test_chat_returns_timeout_error(monkeypatch):
    monkeypatch.setattr(main, "search_documents", lambda query, top_k: sample_evidence())

    def raise_timeout(question, contexts):
        raise ModelTimeoutError("模型响应超时")

    monkeypatch.setattr(main, "generate_answer", raise_timeout)

    response = client.post(
        "/chat",
        json={"question": "绝缘故障应该先做什么？"},
    )

    assert response.status_code == 504
    assert "超时" in response.json()["detail"]


def test_chat_returns_empty_response_error(monkeypatch):
    monkeypatch.setattr(main, "search_documents", lambda query, top_k: sample_evidence())

    def raise_empty_response(question, contexts):
        raise ModelEmptyResponseError("模型返回了空内容")

    monkeypatch.setattr(main, "generate_answer", raise_empty_response)

    response = client.post(
        "/chat",
        json={"question": "绝缘故障应该先做什么？"},
    )

    assert response.status_code == 502
    assert "未返回有效内容" in response.json()["detail"]


def test_chat_rejects_empty_question():
    response = client.post(
        "/chat",
        json={"question": ""},
    )

    assert response.status_code == 422


def test_import_document_and_list_it():
    payload = {
        "title": "测试文档",
        "source": "tests/sample.txt",
        "content": "这是一条用于验证文档导入与查询的测试内容。",
        "source_type": "test",
    }

    create_response = client.post("/documents", json=payload)

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == payload["title"]
    assert created["source_type"] == "test"
    assert created["char_count"] == len(payload["content"])

    list_response = client.get("/documents")

    assert list_response.status_code == 200
    assert any(
        document["document_id"] == created["document_id"]
        for document in list_response.json()
    )


def test_document_rejects_empty_content():
    response = client.post(
        "/documents",
        json={
            "title": "空文档",
            "source": "tests/empty.txt",
            "content": "",
        },
    )

    assert response.status_code == 422


def test_split_text_preserves_overlap():
    text = "".join(str(number % 10) for number in range(300))

    chunks = split_text(text, chunk_size=200, overlap=40)

    assert len(chunks) == 2
    assert len(chunks[0]) == 200
    assert chunks[0][-40:] == chunks[1][:40]


def test_search_rejects_invalid_top_k():
    response = client.post(
        "/search",
        json={
            "query": "绝缘故障",
            "top_k": 0,
        },
    )

    assert response.status_code == 422
