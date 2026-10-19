"""对待审批草稿应用人工决策；不执行正式工单写入。"""

from copy import deepcopy


def _require_text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")
    return value.strip()


def apply_work_order_decision(draft: dict, decision: dict) -> dict:
    """draft 应由 build_work_order_draft 生成；返回独立副本。"""
    if not isinstance(draft, dict) or draft.get("status") != "pending_approval":
        raise ValueError("只能处理 pending_approval 草稿")
    if not isinstance(decision, dict):
        raise ValueError("decision 必须是字典")

    action = decision.get("action")
    if action not in ("approve", "edit", "reject"):
        raise ValueError("action 必须是 approve、edit 或 reject")

    fields = {
        "approve": {"action"},
        "edit": {"action", "changes"},
        "reject": {"action", "reason"},
    }
    if set(decision) != fields[action]:
        raise ValueError(
            f'{action} 决策字段必须为：{"、".join(sorted(fields[action]))}'
        )

    result = deepcopy(draft)
    if action == "approve":
        result["status"] = "approved"
    elif action == "edit":
        changes = decision["changes"]
        if (
            not isinstance(changes, dict)
            or not changes
            or not set(changes) <= {"title", "description"}
        ):
            raise ValueError("changes 必须非空，且只能修改 title 和 description")
        for name, value in changes.items():
            result[name] = _require_text(value, name)
        # 修改内容后，需要针对新内容再次作出明确批准。
        result["status"] = "pending_approval"
    else:
        result["rejection_reason"] = _require_text(decision["reason"], "reason")
        result["status"] = "rejected"

    return result
