"""一次原生工具决策与受控只读执行；不重试、不写工单。"""

from copy import deepcopy
import json
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.task_contracts import EvidencePack, TaskRequest
from app.task_evidence import lookup_charge_reference


PROMPT_VERSION = "week5-tool-choice-v1"
SMOKE_QUESTION = "车辆显示 CP_a054，请查询这份警报资料说明。"
SYSTEM_PROMPT = (
    "你是只读资料查询助手。对于红灯或 CP_a054 的资料问题，先使用所提供的查询工具。"
    "只能选择允许的主题；任务标识、资料路径和权限由服务端控制，不得添加这些参数。"
    "工具返回的是审核摘要，不能据此确认车辆具体故障。范围外问题不调用工具。"
)


class LookupChargeArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    topic: Literal["charge_port_RED", "CP_a054"]


TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "lookup_charge_reference",
        "description": "查询已审核的红灯或 CP_a054 资料摘要，不能确认车辆具体故障。",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": ["charge_port_RED", "CP_a054"]},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
}


class ToolCallRejected(ValueError):
    """仅保留安全原因码，不拼接模型参数或原始异常文本。"""


def build_tool_request(question: str, model: str) -> dict:
    question = TaskRequest(question=question).question
    if not isinstance(model, str) or not model.strip():
        raise ValueError("invalid_model")
    return {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "tools": [deepcopy(TOOL_SPEC)],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "enable_thinking": False,
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolCallRejected("duplicate_argument_key")
        result[key] = value
    return result


def parse_lookup_call(message: dict) -> tuple[str, LookupChargeArgs]:
    if not isinstance(message, dict):
        raise ToolCallRejected("invalid_message")
    calls = message.get("tool_calls")
    if calls is None or calls == []:
        raise ToolCallRejected("no_tool_call")
    if not isinstance(calls, list):
        raise ToolCallRejected("invalid_tool_calls")
    if len(calls) != 1:
        raise ToolCallRejected("tool_call_budget_exceeded")
    call = calls[0]
    if not isinstance(call, dict) or call.get("type") != "function":
        raise ToolCallRejected("invalid_tool_call")
    call_id = call.get("id")
    if not isinstance(call_id, str) or not call_id.strip():
        raise ToolCallRejected("missing_call_id")
    function = call.get("function")
    if not isinstance(function, dict) or function.get("name") != "lookup_charge_reference":
        raise ToolCallRejected("unknown_function")
    raw = function.get("arguments")
    if not isinstance(raw, str):
        raise ToolCallRejected("invalid_arguments_json")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ToolCallRejected):
            raise
        raise ToolCallRejected("invalid_arguments_json") from error
    try:
        arguments = LookupChargeArgs.model_validate(payload)
    except ValidationError as error:
        raise ToolCallRejected("invalid_arguments_schema") from error
    return call_id, arguments


def _redact(value, secret: str):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {_redact(key, secret): _redact(item, secret) for key, item in value.items()}
    return value


def run_tool_choice(
    question: str, *, model: str, base_url: str, api_key: str,
    task_id: str, post=None, lookup=None,
) -> dict:
    """注入入口仅供离线测试；模型只能提供 LookupChargeArgs。"""
    record = {
        "outcome": "request_failed",
        "reason": None,
        "transport_kind": "injected_test_transport" if post is not None else "real_http_transport",
        "task_id": task_id,
        "requested_model": model,
        "returned_model": None,
        "resolved_model_snapshot": None,
        "prompt_version": PROMPT_VERSION,
        "request_payload": None,
        "endpoint": None,
        "model_request_attempts": 0,
        "http_status": None,
        "request_elapsed_seconds": None,
        "provider_response": None,
        "usage": None,
        "actual_cost": None,
        "argument_validation": "not_run",
        "selected_topic": None,
        "tool_call_id": None,
        "tool_execution_attempts": 0,
        "tool_elapsed_seconds": None,
        "evidence": None,
    }
    if not isinstance(api_key, str) or not api_key.strip():
        record["reason"] = "missing_api_key"
        return _redact(record, api_key if isinstance(api_key, str) else "")
    try:
        task = EvidencePack(task_id=task_id)
        payload = build_tool_request(question, model)
        url = httpx.URL(base_url)
        if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
            raise ValueError("invalid_endpoint")
        endpoint = f"{str(url).rstrip('/')}/chat/completions"
    except (ValueError, TypeError, httpx.InvalidURL):
        record["reason"] = "invalid_configuration"
        return _redact(record, api_key)
    record.update(task_id=task.task_id, request_payload=payload, endpoint=endpoint)
    send = httpx.post if post is None else post
    execute = lookup_charge_reference if lookup is None else lookup
    started = perf_counter()
    record["model_request_attempts"] = 1
    try:
        response = send(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=20.0,
        )
        record["http_status"] = response.status_code
        response.raise_for_status()
        body = response.json()
    except httpx.TimeoutException:
        record["reason"] = "model_timeout"
    except httpx.HTTPStatusError:
        record["reason"] = "model_http_error"
    except httpx.HTTPError:
        record["reason"] = "model_transport_error"
    except ValueError:
        record["reason"] = "invalid_response_json"
    finally:
        record["request_elapsed_seconds"] = perf_counter() - started
    if record["reason"] is not None:
        return _redact(record, api_key)
    if isinstance(body, dict):
        record["returned_model"] = body.get("model")
        record["usage"] = body.get("usage")
    try:
        choices = body["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("invalid_choices")
        message = choices[0]["message"]
        record["provider_response"] = {
            "id": body.get("id"),
            "finish_reason": choices[0].get("finish_reason"),
            "message": {
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            },
        }
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        record.update(outcome="blocked", reason="invalid_response_shape")
        return _redact(record, api_key)
    try:
        call_id, arguments = parse_lookup_call(message)
    except ToolCallRejected as error:
        reason = str(error)
        record.update(
            outcome="no_tool_call" if reason == "no_tool_call" else "blocked",
            reason=reason, argument_validation="not_run" if reason == "no_tool_call" else "rejected",
        )
        return _redact(record, api_key)
    record.update(
        argument_validation="passed", selected_topic=arguments.topic, tool_call_id=call_id,
        tool_execution_attempts=1,
    )
    started = perf_counter()
    try:
        evidence = execute(arguments.topic, task_id=task.task_id)
        if not isinstance(evidence, EvidencePack):
            raise ValueError("invalid_tool_output")
        evidence = EvidencePack.model_validate(evidence.model_dump())
        if evidence.task_id != task.task_id:
            raise ValueError("tool_task_mismatch")
        record.update(outcome="tool_executed", evidence=evidence.model_dump(mode="json"))
    except Exception as error:
        record.update(outcome="tool_failed", reason="read_only_tool_error", tool_error_type=type(error).__name__)
    finally:
        record["tool_elapsed_seconds"] = perf_counter() - started
    return _redact(record, api_key)
