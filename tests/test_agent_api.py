import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from app import agent_api, diagnostic_tools, tool_router
from app.diagnosis_graph import build_diagnosis_graph


def request_body(**overrides):
    body = {
        "vehicle_id": "VIN-DEMO-001", "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
    }
    body.update(overrides)
    return body


@pytest.fixture
def client():
    before = dict(agent_api.app.dependency_overrides)
    graph = build_diagnosis_graph(dtc_lookup=diagnostic_tools.lookup_dtc)
    agent_api.app.dependency_overrides[agent_api.get_diagnosis_graph] = lambda: graph
    agent_api.app.dependency_overrides[agent_api.get_knowledge_chunks] = lambda: []
    try:
        with TestClient(agent_api.app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        agent_api.app.dependency_overrides.clear()
        agent_api.app.dependency_overrides.update(before)


def test_health_does_not_resolve_graph_or_corpus_dependencies(client):
    def forbidden():
        pytest.fail("存活检查不应调用诊断依赖")
    agent_api.app.dependency_overrides[agent_api.get_diagnosis_graph] = forbidden
    agent_api.app.dependency_overrides[agent_api.get_knowledge_chunks] = forbidden
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_diagnose_returns_no_evidence_without_exposing_internal_corpus(client):
    response = client.post("/diagnose", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_evidence"
    assert body["tool_data_source"] == "mock"
    assert body["tool_call_count"] == 1
    assert body["citations"] == []
    assert body["tool_trace"] == [{"tool_name": "lookup_dtc", "status": "success"}]
    assert "knowledge_chunks" not in body
    assert "seen_tool_calls" not in body


def test_diagnose_returns_fixture_candidates_with_their_sources(client):
    chunk = {
        "chunk_id": "api-demo:0", "document_id": "api-demo", "source": "demo/api",
        "text": "P0AA6 教学片段，仅用于验证 HTTP 返回和引用。",
    }
    agent_api.app.dependency_overrides[agent_api.get_knowledge_chunks] = lambda: [chunk]
    response = client.post("/diagnose", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert chunk["text"] in body["answer"]
    assert body["citations"] == [{key: chunk[key] for key in ("chunk_id", "document_id", "source")}]


def test_missing_fields_request_clarification_instead_of_using_demo_defaults(client):
    response = client.post("/diagnose", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_info"
    assert body["missing_fields"] == ["vehicle_id", "symptom", "dtc_codes"]
    assert body["tool_call_count"] == 0
    assert body["tool_trace"] == []


def test_inventory_requires_a_part_number_in_the_request(client):
    response = client.post("/diagnose", json=request_body(requested_tool="lookup_inventory"))
    assert response.json()["status"] == "needs_info"
    assert response.json()["missing_fields"] == ["part_number"]
    assert response.json()["tool_call_count"] == 0


@pytest.mark.parametrize("tool, extra", [
    ("lookup_vehicle_history", {}),
    ("lookup_inventory", {"part_number": "HV-ISO-SENSOR-01"}),
])
def test_other_readonly_tools_can_be_queried(client, tool, extra):
    response = client.post("/diagnose", json=request_body(requested_tool=tool, **extra))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["tool_trace"] == [{"tool_name": tool, "status": "success"}]


@pytest.mark.parametrize("overrides", [
    {"requested_tool": "delete_work_order"},
    {"dtc_codes": "P0AA6"},
    {"dtc_codes": [123]},
    {"dtc_codes": ["P0AA6", "P0123"]},
    {"tool_call_count": 999},
    {"knowledge_chunks": [{"text": "客户端提供的假证据"}]},
    {"citations": [{"source": "伪造引用"}]},
])
def test_invalid_or_internal_state_inputs_are_rejected(client, overrides):
    response = client.post("/diagnose", json=request_body(**overrides))
    assert response.status_code == 422


def test_known_tool_failure_returns_a_review_request(client):
    def fail(**arguments):
        raise TimeoutError("离线测试注入超时")
    graph = build_diagnosis_graph(dtc_lookup=fail)
    agent_api.app.dependency_overrides[agent_api.get_diagnosis_graph] = lambda: graph
    response = client.post("/diagnose", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_human"
    assert body["stop_reason"] == "tool_timeout"
    assert body["handoff_request"]["reason"] == "tool_timeout"
    assert body["citations"] == []


def test_unexpected_program_error_is_an_http_error_instead_of_a_diagnosis(client):
    def broken(**arguments):
        raise RuntimeError("程序缺陷")
    graph = build_diagnosis_graph(dtc_lookup=broken)
    agent_api.app.dependency_overrides[agent_api.get_diagnosis_graph] = lambda: graph
    response = client.post("/diagnose", json=request_body())
    assert response.status_code == 500


def test_unavailable_corpus_has_an_explanatory_503(client, monkeypatch):
    from app import knowledge_corpus
    def unavailable():
        raise ValueError("语料哈希不一致")
    monkeypatch.setattr(knowledge_corpus, "load_knowledge_chunks", unavailable)
    agent_api.app.dependency_overrides.pop(agent_api.get_knowledge_chunks)
    response = client.post("/diagnose", json=request_body())
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "corpus_unavailable"


def test_reusing_the_compiled_graph_does_not_share_request_budget(client):
    first = client.post("/diagnose", json=request_body()).json()
    second = client.post("/diagnose", json=request_body()).json()
    assert first["tool_call_count"] == second["tool_call_count"] == 1
    assert first["status"] == second["status"] == "no_evidence"
    assert first["trace"] == second["trace"]


def test_default_http_dependency_really_queries_the_mcp_subprocess(client, monkeypatch):
    def forbidden_local(**arguments):
        raise AssertionError("不应使用进程内 DTC 查询")
    monkeypatch.setitem(tool_router.TOOL_REGISTRY, "lookup_dtc", forbidden_local)
    agent_api.app.dependency_overrides.pop(agent_api.get_diagnosis_graph)
    agent_api.get_diagnosis_graph.cache_clear()
    try:
        response = client.post("/diagnose", json=request_body())
        assert response.status_code == 200
        assert response.json()["status"] == "no_evidence"
        assert response.json()["tool_trace"][0]["status"] == "success"
    finally:
        agent_api.get_diagnosis_graph.cache_clear()


def test_import_and_health_do_not_load_legacy_embedding_or_llm_modules():
    program = """
import json
import sys
from fastapi.testclient import TestClient
from app.agent_api import app
with TestClient(app) as client:
    assert client.get('/health').json() == {'status': 'ok'}
print(json.dumps({name: name in sys.modules for name in ('chromadb', 'sentence_transformers', 'app.llm')}))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program], capture_output=True, text=True,
        cwd=Path(__file__).resolve().parent.parent, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "chromadb": False, "sentence_transformers": False, "app.llm": False,
    }
