"""离线模拟 HTTP/工具响应；这些结果不计为真实模型调用。"""

from copy import deepcopy
import json

import httpx
import pytest

from app import task_tool_calling as calling
from app.task_contracts import EvidenceItem, EvidencePack
from scripts import week5_tool_call_smoke as smoke


@pytest.fixture(autouse=True)
def block_uninjected_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("离线测试禁止真实网络请求")
    monkeypatch.setattr(httpx, "post", blocked)


def native_message(arguments='{"topic": "CP_a054"}', *, name="lookup_charge_reference"):
    return {
        "content": None,
        "tool_calls": [{
            "id": "mock-call-001", "type": "function",
            "function": {"name": name, "arguments": arguments},
        }],
    }


def provider_body(message=None):
    return {
        "id": "mock-response-001", "model": "mock-returned-model",
        "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        "choices": [{
            "finish_reason": "tool_calls",
            "message": native_message() if message is None else message,
        }],
    }


def fake_http(body, *, status=200):
    requests = []

    def post(url, **kwargs):
        requests.append((url, deepcopy(kwargs)))
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    return post, requests


def fake_lookup():
    calls = []

    def lookup(topic, *, task_id):
        calls.append((topic, task_id))
        return EvidencePack(task_id=task_id, items=[EvidenceItem(
            chunk_id="mock-only:0", document_id="mock-only", source="mock://fixture",
            text="模拟工具结果，不是真实车辆或审核摘要。", material_kind="mock",
        )])

    return lookup, calls


def run(post, lookup, **changes):
    configuration = {
        "model": "mock-requested-model", "base_url": "https://example.org/v1",
        "api_key": "mock-secret-key", "task_id": "task_server_owned",
        "post": post, "lookup": lookup,
    }
    configuration.update(changes)
    return calling.run_tool_choice(calling.SMOKE_QUESTION, **configuration)


def test_request_uses_auto_choice_and_exposes_only_topic_without_shared_schema_mutation():
    first = calling.build_tool_request(calling.SMOKE_QUESTION, "mock-model")
    parameters = first["tools"][0]["function"]["parameters"]
    assert set(parameters["properties"]) == {"topic"}
    assert parameters["additionalProperties"] is False
    assert first["tool_choice"] == "auto"
    assert first["parallel_tool_calls"] is False
    assert first["enable_thinking"] is False
    del parameters["properties"]["topic"]
    second = calling.build_tool_request(calling.SMOKE_QUESTION, "mock-model")
    assert "topic" in second["tools"][0]["function"]["parameters"]["properties"]


def test_valid_native_call_executes_once_with_the_server_task_and_preserves_usage():
    body = provider_body()
    before = deepcopy(body)
    post, requests = fake_http(body)
    lookup, calls = fake_lookup()

    result = run(post, lookup)

    assert result["outcome"] == "tool_executed"
    assert len(requests) == result["model_request_attempts"] == 1
    assert calls == [("CP_a054", "task_server_owned")]
    assert result["tool_execution_attempts"] == 1
    assert result["argument_validation"] == "passed"
    assert result["usage"] == body["usage"]
    assert result["requested_model"] == "mock-requested-model"
    assert result["returned_model"] == "mock-returned-model"
    assert result["actual_cost"] is None
    assert result["resolved_model_snapshot"] is None
    assert result["evidence"]["items"][0]["material_kind"] == "mock"
    assert result["transport_kind"] == "injected_test_transport"
    assert "mock-secret-key" not in json.dumps(result)
    assert body == before


@pytest.mark.parametrize("message, reason", [
    ({"content": '{"topic":"CP_a054"}'}, "no_tool_call"),
    ({"tool_calls": []}, "no_tool_call"),
    ({"tool_calls": native_message()["tool_calls"] * 2}, "tool_call_budget_exceeded"),
    ({"tool_calls": "invalid"}, "invalid_tool_calls"),
    (native_message(name="create_work_order"), "unknown_function"),
    (native_message("{"), "invalid_arguments_json"),
    (native_message({"topic": "CP_a054"}), "invalid_arguments_json"),
    (native_message("[]"), "invalid_arguments_schema"),
    (native_message("null"), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a053"}'), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a054","task_id":"task_other"}'), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a054","source_path":"/tmp/secret"}'), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a054","approved":true}'), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a054","requested_tool":"create_work_order"}'), "invalid_arguments_schema"),
    (native_message('{"topic":"CP_a054","topic":"charge_port_RED"}'), "duplicate_argument_key"),
])
def test_untrusted_calls_are_blocked_before_any_tool_execution(message, reason):
    post, requests = fake_http(provider_body(message))
    lookup, calls = fake_lookup()

    result = run(post, lookup)

    assert result["reason"] == reason
    assert result["outcome"] == ("no_tool_call" if reason == "no_tool_call" else "blocked")
    assert len(requests) == 1
    assert result["tool_execution_attempts"] == 0
    assert calls == []


@pytest.mark.parametrize("field, value, reason", [
    ("id", None, "missing_call_id"),
    ("type", "custom", "invalid_tool_call"),
])
def test_native_call_requires_a_function_type_and_call_identifier(field, value, reason):
    message = native_message()
    message["tool_calls"][0][field] = value
    post, _ = fake_http(provider_body(message))
    lookup, calls = fake_lookup()
    result = run(post, lookup)
    assert result["reason"] == reason
    assert calls == []


@pytest.mark.parametrize("error, reason", [
    (httpx.ReadTimeout("mock-secret-key"), "model_timeout"),
    (httpx.ConnectError("mock-secret-key"), "model_transport_error"),
])
def test_transport_failures_do_not_retry_or_execute_tools(error, reason):
    requests = []
    def post(*args, **kwargs):
        requests.append(1)
        raise error
    lookup, calls = fake_lookup()
    result = run(post, lookup)
    assert len(requests) == 1
    assert result["outcome"] == "request_failed"
    assert result["reason"] == reason
    assert result["tool_execution_attempts"] == 0
    assert calls == []
    assert "mock-secret-key" not in json.dumps(result)


def test_http_error_keeps_status_without_logging_body_headers_or_secret():
    post, requests = fake_http({"error": "mock-secret-key"}, status=403)
    lookup, calls = fake_lookup()
    result = run(post, lookup)
    assert len(requests) == 1
    assert result["http_status"] == 403
    assert result["reason"] == "model_http_error"
    assert result["usage"] is None
    assert calls == []
    assert "Authorization" not in json.dumps(result)
    assert "mock-secret-key" not in json.dumps(result)


@pytest.mark.parametrize("body", [[], {}, {"choices": []}, provider_body("bad-message")])
def test_malformed_provider_shape_cannot_execute_tools(body):
    post, _ = fake_http(body)
    lookup, calls = fake_lookup()
    result = run(post, lookup)
    assert result["outcome"] == "blocked"
    assert result["reason"] == "invalid_response_shape"
    assert calls == []


def test_invalid_response_json_is_recorded_without_tool_execution():
    def post(url, **kwargs):
        return httpx.Response(200, text="{", request=httpx.Request("POST", url))
    lookup, calls = fake_lookup()
    result = run(post, lookup)
    assert result["reason"] == "invalid_response_json"
    assert calls == []


@pytest.mark.parametrize("changes, reason", [
    ({"api_key": ""}, "missing_api_key"),
    ({"base_url": "https://example.org/v1?token=secret"}, "invalid_configuration"),
    ({"task_id": " "}, "invalid_configuration"),
])
def test_invalid_configuration_is_rejected_before_http(changes, reason):
    post, requests = fake_http(provider_body())
    lookup, calls = fake_lookup()
    result = run(post, lookup, **changes)
    assert result["reason"] == reason
    assert result["model_request_attempts"] == 0
    assert requests == calls == []


def test_no_usage_stays_unknown_and_echoed_secret_is_redacted():
    body = provider_body()
    del body["usage"]
    body["choices"][0]["message"]["content"] = "mock-secret-key"
    post, _ = fake_http(body)
    lookup, _ = fake_lookup()
    result = run(post, lookup)
    assert result["outcome"] == "tool_executed"
    assert result["usage"] is None
    assert result["actual_cost"] is None
    assert result["provider_response"]["message"]["content"] == "[REDACTED]"


def test_tool_failure_is_recorded_once_without_error_text_or_retry():
    post, requests = fake_http(provider_body())
    calls = []
    def lookup(*args, **kwargs):
        calls.append(1)
        raise ValueError("mock-secret-key")
    result = run(post, lookup)
    assert len(requests) == len(calls) == 1
    assert result["outcome"] == "tool_failed"
    assert result["tool_error_type"] == "ValueError"
    assert "mock-secret-key" not in json.dumps(result)


def test_tool_output_must_belong_to_the_current_server_task():
    post, _ = fake_http(provider_body())
    def lookup(*args, **kwargs):
        return EvidencePack(task_id="task_other")
    result = run(post, lookup)
    assert result["outcome"] == "tool_failed"
    assert result["evidence"] is None


@pytest.mark.parametrize("topic, expected_exit", [("CP_a054", 0), ("charge_port_RED", 1)])
def test_cli_saves_distinct_mock_records_and_does_not_rewrite_wrong_selection(
    tmp_path, monkeypatch, topic, expected_exit,
):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "mock-secret-key")
    post, requests = fake_http(provider_body(native_message(json.dumps({"topic": topic}))))
    lookup, calls = fake_lookup()
    def offline_run(question, **configuration):
        return calling.run_tool_choice(question, **configuration, post=post, lookup=lookup)
    monkeypatch.setattr(smoke, "run_tool_choice", offline_run)

    assert smoke.main(["--output-dir", str(tmp_path)]) == expected_exit
    first_path = next(tmp_path.glob("tool_call_smoke_*.json"))
    first_bytes = first_path.read_bytes()
    assert smoke.main(["--output-dir", str(tmp_path)]) == expected_exit

    assert len(list(tmp_path.glob("tool_call_smoke_*.json"))) == 2
    assert first_path.read_bytes() == first_bytes
    record = json.loads(first_bytes)
    assert record["selected_topic"] == topic
    assert record["scenario_passed"] is (expected_exit == 0)
    assert record["transport_kind"] == "injected_test_transport"
    assert record["timezone"] == "Asia/Shanghai"
    assert record["versions"]["tool_schema_sha256"]
    assert record["formal_work_order_written"] is False
    assert len(requests) == len(calls) == 2
    assert "mock-secret-key" not in first_bytes.decode()
