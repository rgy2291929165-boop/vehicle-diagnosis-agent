"""离线模拟两阶段模型响应，不作为真实模型或业务成功率证据。"""

from copy import deepcopy
import json

import httpx
import pytest

from app import task_read_only as read_only
from app.task_contracts import EvidenceItem, EvidencePack
from scripts import week5_read_only_smoke as smoke


@pytest.fixture(autouse=True)
def block_uninjected_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("离线测试禁止真实网络请求")
    monkeypatch.setattr(httpx, "post", blocked)


def selection_response(*, topic="CP_a054", no_tool=False):
    message = {"content": ""}
    if not no_tool:
        message["tool_calls"] = [{
            "id": "mock-call-001", "type": "function", "index": 0,
            "function": {
                "name": "lookup_charge_reference",
                "arguments": json.dumps({"topic": topic}),
            },
        }]
    return {
        "id": "mock-selection", "model": "mock-returned",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "choices": [{"message": message, "finish_reason": "stop" if no_tool else "tool_calls"}],
    }


def answer_payload():
    return {
        "status": "answer", "message": "合成解释，只用于验证结构与引用。",
        "citations": ["mock-reference:0"], "missing_fields": [],
    }


def answer_response(content=None):
    return {
        "id": "mock-answer", "model": "mock-returned",
        "usage": {"prompt_tokens": 20, "completion_tokens": 6, "total_tokens": 26},
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps(answer_payload(), ensure_ascii=False) if content is None else content},
        }],
    }


def fake_transport(responses):
    calls = []
    def post(url, **kwargs):
        calls.append((url, deepcopy(kwargs)))
        assert len(calls) <= len(responses), "请求次数超过本测试预算"
        item = responses[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item, request=httpx.Request("POST", url))
    return post, calls


def fake_tool():
    calls = []
    def lookup(topic, *, task_id):
        calls.append((topic, task_id))
        return EvidencePack(task_id=task_id, items=[EvidenceItem(
            chunk_id="mock-reference:0", document_id="mock-reference",
            source="mock://fixture", text="模拟资料，不是真实车辆数据。",
            material_kind="mock", limitations=["仅为合成契约样例"],
        )])
    return lookup, calls


def run(post, lookup):
    return read_only.run_read_only_task(
        read_only.READ_ONLY_QUESTION,
        model="mock-model", base_url="https://example.org/v1",
        api_key="mock-secret-key", task_id="task_server_owned", post=post, lookup=lookup,
    )


def test_two_stage_flow_projects_only_current_evidence_and_preserves_native_call_pair():
    bodies = [selection_response(), answer_response()]
    before = deepcopy(bodies)
    post, requests = fake_transport(bodies)
    lookup, tool_calls = fake_tool()
    result = run(post, lookup)
    assert len(requests) == result["model_request_attempts"] == 2
    assert tool_calls == [("CP_a054", "task_server_owned")]
    assert result["tool_execution_attempts"] == 1
    assert result["outcome"] == "answer_validated"
    assert result["final_result"]["task_id"] == "task_server_owned"
    assert result["final_result"]["citations"] == ["mock-reference:0"]
    assert result["citation_check"] == result["output_validation"] == "passed"
    assert result["semantic_review"] == "pending_human_check"
    assert result["usage_total"] == {"prompt_tokens": 30, "completion_tokens": 11, "total_tokens": 41}
    assert result["actual_cost"] is None
    second = requests[1][1]["json"]
    assert second["tool_choice"] == "none"
    assert second["response_format"] == {"type": "json_object"}
    assert second["enable_thinking"] is False
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "tool"]
    assistant, tool = second["messages"][2:]
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"] == "mock-call-001"
    assert "index" not in assistant["tool_calls"][0]
    context = json.loads(tool["content"])
    assert set(context) == {"items", "gaps"}
    assert context["items"][0]["material_kind"] == "mock"
    assert context["items"][0]["limitations"] == ["仅为合成契约样例"]
    assert "task_server_owned" not in json.dumps(second)
    assert "mock-secret-key" not in json.dumps(result)
    assert bodies == before


def test_failed_selection_does_not_send_a_second_model_request():
    post, requests = fake_transport([selection_response(no_tool=True)])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert len(requests) == 1
    assert calls == []
    assert result["stages"]["answer"] is None
    assert result["final_result"]["status"] == "needs_human"
    assert result["reason"] == "no_tool_call"


@pytest.mark.parametrize("mode", ["empty", "other_task", "error"])
def test_unusable_tool_result_stops_before_answer_generation(mode):
    post, requests = fake_transport([selection_response()])
    tool_calls = []
    def lookup(topic, *, task_id):
        tool_calls.append((topic, task_id))
        if mode == "error":
            raise ValueError("mock-secret-key")
        return EvidencePack(task_id="task_other" if mode == "other_task" else task_id)
    result = run(post, lookup)
    assert len(requests) == len(tool_calls) == 1
    assert result["model_request_attempts"] == 1
    assert result["stages"]["answer"] is None
    assert result["final_result"]["status"] == "needs_human"
    assert "mock-secret-key" not in json.dumps(result)


@pytest.mark.parametrize("content, reason", [
    ("{", "invalid_answer_json"),
    (chr(96) * 3 + "json\n{}\n" + chr(96) * 3, "invalid_answer_json"),
    ("[]", "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "citations": ["missing:0"]}), "invalid_answer_reference"),
    (json.dumps({**answer_payload(), "citations": []}), "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "task_id": "task_other"}), "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "approved": True}), "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "work_order_id": "forged-order"}), "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "status": "submitted"}), "invalid_answer_schema"),
    (json.dumps({**answer_payload(), "status": "needs_info", "missing_fields": []}), "invalid_answer_schema"),
    ('{"status":"answer","status":"needs_human","message":"重复字段"}', "duplicate_answer_key"),
])
def test_invalid_answer_is_audited_but_never_becomes_the_final_user_result(content, reason):
    post, requests = fake_transport([selection_response(), answer_response(content)])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert len(requests) == 2
    assert len(calls) == 1
    assert result["reason"] == reason
    assert result["candidate_output"] == content
    assert result["final_result"]["status"] == "needs_human"
    assert result["final_result"]["message"] == read_only.FALLBACK_MESSAGE
    assert result["final_result"]["citations"] == []
    assert result["output_validation"] == "rejected"


def test_extra_answer_tool_call_never_triggers_another_lookup_or_model_request():
    response = answer_response()
    response["choices"][0]["message"]["tool_calls"] = [
        {"id": "mock-extra", "type": "function", "function": {"name": "create_work_order", "arguments": "{}"}},
    ]
    post, requests = fake_transport([selection_response(), response])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert len(requests) == 2 and len(calls) == 1
    assert result["reason"] == "additional_tool_call"
    assert result["final_result"]["status"] == "needs_human"


def test_truncated_answer_is_not_accepted_even_if_its_json_is_balanced():
    response = answer_response()
    response["choices"][0]["finish_reason"] = "length"
    post, requests = fake_transport([selection_response(), response])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert result["reason"] == "answer_not_completed"
    assert result["final_result"]["status"] == "needs_human"
    assert len(requests) == 2 and len(calls) == 1


@pytest.mark.parametrize("error, reason", [
    (httpx.ReadTimeout("mock-secret-key"), "answer_timeout"),
    (httpx.ConnectError("mock-secret-key"), "answer_transport_error"),
    (httpx.Response(400, json={"error": "mock-secret-key"}, request=httpx.Request("POST", "https://example.org")), "answer_http_error"),
    (httpx.Response(200, text="{", request=httpx.Request("POST", "https://example.org")), "invalid_answer_response_json"),
])
def test_second_request_failures_count_the_attempt_and_never_retry(error, reason):
    post, requests = fake_transport([selection_response(), error])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert len(requests) == result["model_request_attempts"] == 2
    assert len(calls) == result["tool_execution_attempts"] == 1
    assert result["reason"] == reason
    assert result["final_result"]["status"] == "needs_human"
    assert result["usage_total"] is None
    assert result["known_partial_token_totals"] == {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
    }
    assert "mock-secret-key" not in json.dumps(result)


@pytest.mark.parametrize("body", [{}, [], {"choices": []}, {"choices": [{"message": None}]}])
def test_malformed_answer_response_cannot_bypass_the_output_gate(body):
    post, requests = fake_transport([selection_response(), body])
    lookup, calls = fake_tool()
    result = run(post, lookup)
    assert result["reason"] == "invalid_answer_response_shape"
    assert result["final_result"]["status"] == "needs_human"
    assert len(requests) == 2 and len(calls) == 1


def test_missing_usage_is_unknown_and_known_partial_usage_is_not_dropped():
    response = answer_response()
    del response["usage"]
    post, _ = fake_transport([selection_response(), response])
    lookup, _ = fake_tool()
    result = run(post, lookup)
    assert result["outcome"] == "answer_validated"
    assert result["usage_complete"] is False
    assert result["usage_total"] is None
    assert result["known_partial_token_totals"]["total_tokens"] == 15
    assert result["stages"]["answer"]["usage"] is None


def test_valid_model_referral_is_not_rewritten_into_an_answer():
    payload = {"status": "needs_human", "message": "合成转人工说明", "citations": [], "missing_fields": []}
    post, _ = fake_transport([selection_response(), answer_response(json.dumps(payload))])
    lookup, _ = fake_tool()
    result = run(post, lookup)
    assert result["outcome"] == "needs_human"
    assert result["reason"] is None
    assert result["output_validation"] == "passed"
    assert result["final_result"]["message"] == "合成转人工说明"


def test_parse_result_binds_the_server_task_and_rejects_another_tasks_pack():
    evidence = EvidencePack(task_id="task_other")
    content = json.dumps({"status": "needs_human", "message": "合成说明"})
    with pytest.raises(read_only.AnswerRejected, match="invalid_answer_reference"):
        read_only.parse_read_only_answer(content, task_id="task_server_owned", evidence=evidence)


def test_structure_pass_is_explicitly_separate_from_semantic_approval():
    payload = answer_payload()
    payload["message"] = "合成负例：电池已损坏。"
    post, _ = fake_transport([selection_response(), answer_response(json.dumps(payload))])
    lookup, _ = fake_tool()
    result = run(post, lookup)
    assert result["output_validation"] == result["citation_check"] == "passed"
    assert result["semantic_review"] == "pending_human_check"
    # 本测试揭示结构门禁的边界，不将此错误主张计为正确诊断。


@pytest.mark.parametrize("topic, expected_exit", [("CP_a054", 0), ("charge_port_RED", 1)])
def test_cli_saves_mock_trace_without_overwriting_or_promoting_wrong_topic(
    tmp_path, monkeypatch, topic, expected_exit,
):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "mock-secret-key")
    post, requests = fake_transport([
        selection_response(topic=topic), answer_response(),
        selection_response(topic=topic), answer_response(),
    ])
    lookup, calls = fake_tool()
    def offline_run(question, **configuration):
        return read_only.run_read_only_task(question, **configuration, post=post, lookup=lookup)
    monkeypatch.setattr(smoke, "run_read_only_task", offline_run)
    assert smoke.main(["--output-dir", str(tmp_path)]) == expected_exit
    first_path = next(tmp_path.glob("read_only_smoke_*.json"))
    first_bytes = first_path.read_bytes()
    assert smoke.main(["--output-dir", str(tmp_path)]) == expected_exit
    assert len(list(tmp_path.glob("read_only_smoke_*.json"))) == 2
    assert first_path.read_bytes() == first_bytes
    record = json.loads(first_bytes)
    assert record["selected_topic"] == topic
    assert record["scenario_structure_passed"] is (expected_exit == 0)
    assert record["semantic_review"] == "pending_human_check"
    assert record["transport_kind"] == "injected_test_transport"
    assert record["thread_id"] == record["task_id"]
    assert record["formal_work_order_written"] is False
    assert "app/task_read_only.py" in record["versions"]["file_sha256"]
    assert "mock-secret-key" not in first_bytes.decode()
    assert len(requests) == 4 and len(calls) == 2
