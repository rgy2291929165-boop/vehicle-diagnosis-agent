"""仅根据用户提供的故障信息生成待审批草稿；无工具调用或持久化。"""


def build_work_order_draft(state: dict) -> dict:
    fields = {}
    for name in ("vehicle_id", "symptom"):
        value = state.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} 不能为空，且必须是字符串")
        fields[name] = value.strip()

    codes = state.get("dtc_codes")
    if (
        not isinstance(codes, list)
        or not codes
        or any(not isinstance(code, str) or not code.strip() for code in codes)
    ):
        raise ValueError("dtc_codes 必须是非空的故障码字符串列表")

    normalized_codes = [code.strip().upper() for code in codes]
    return {
        "vehicle_id": fields["vehicle_id"],
        "symptom": fields["symptom"],
        "dtc_codes": normalized_codes,
        "title": "车辆故障人工复核",
        "description": (
            f'用户报告的故障现象：{fields["symptom"]}。'
            f'用户提供的故障码：{"、".join(normalized_codes)}。'
            "请人工核实故障信息并安排后续检查。"
        ),
        "status": "pending_approval",
    }
