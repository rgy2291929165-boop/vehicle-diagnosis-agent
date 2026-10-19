"""为单次诊断建立独立初始状态，供服务与教学脚本共同使用。"""


def make_diagnosis_state(chunks: list[dict], **overrides) -> dict:
    state = {
        "vehicle_id": "VIN-DEMO-001",
        "symptom": "仪表提示绝缘故障",
        "dtc_codes": ["P0AA6"],
        "part_number": "HV-ISO-SENSOR-01",
        "requested_tool": "lookup_dtc",
        "missing_fields": [],
        "next_action": "ask_clarifying_question",
        "clarifying_question": None,
        "tool_call": None,
        "tool_result": None,
        "tool_trace": [],
        "answer": "",
        "trace": [],
        "tool_call_count": 0,
        "max_tool_calls": 2,
        "seen_tool_calls": [],
        "status": "running",
        "stop_reason": None,
        "knowledge_chunks": chunks,
        "retrieval_query": "",
        "retrieved_chunks": [],
        "citations": [],
        "handoff_request": None,
    }
    state.update(overrides)
    return state
