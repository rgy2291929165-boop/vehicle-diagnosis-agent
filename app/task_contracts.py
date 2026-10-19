"""第五周任务契约：区分输入、标识、证据、只读结果与待审批草稿。"""

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class TaskRequest(BaseModel):
    """格式合法的请求仍可能缺少业务信息；补问与授权由后续流程负责。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    question: LongText
    vehicle_id: ShortText | None = None
    vehicle_model: ShortText | None = None
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    market_region: ShortText | None = None
    symptom: LongText | None = None
    alert_code: ShortText | None = None
    dtc_codes: list[ShortText] = Field(default_factory=list, max_length=10)


class TaskIdentity(BaseModel):
    """服务端关联业务任务与图线程的标识，不授予访问或审批权限。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: ShortText
    thread_id: ShortText


def new_task_identity() -> TaskIdentity:
    """仅在创建任务时调用；后续请求应使用已保存的标识。"""
    task_id = f"task_{uuid4().hex}"
    return TaskIdentity(task_id=task_id, thread_id=task_id)


class EvidenceItem(BaseModel):
    """保留来源、材料种类与局限；格式合法不代表内容或适用性已确认。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    chunk_id: ShortText
    document_id: ShortText
    source: LongText
    text: LongText
    material_kind: Literal["reviewed_summary", "limited_excerpt", "mock"]
    limitations: list[LongText] = Field(default_factory=list, max_length=20)


class EvidencePack(BaseModel):
    """当前任务的证据与缺口，不包含诊断结论或审批权限。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: ShortText
    items: list[EvidenceItem] = Field(default_factory=list, max_length=10)
    gaps: list[LongText] = Field(default_factory=list, max_length=20)


class TaskResult(BaseModel):
    """只读结果的结构约束，不授予审批或提交权限。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: ShortText
    status: Literal["answer", "needs_info", "needs_human"]
    message: LongText
    citations: list[ShortText] = Field(default_factory=list, max_length=10)
    missing_fields: list[ShortText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_status_details(self) -> "TaskResult":
        if self.status == "answer" and not self.citations:
            raise ValueError("answer 结果必须至少有一条引用")
        if self.status == "needs_info" and not self.missing_fields:
            raise ValueError("needs_info 结果必须说明缺少哪些字段")
        return self


def validate_result_evidence(result: TaskResult, evidence: EvidencePack) -> None:
    """显式核对任务归属与引用存在性；不验证主张是否受到证据支持。"""
    if result.task_id != evidence.task_id:
        raise ValueError("结果与证据包必须属于同一任务")

    available_ids = {item.chunk_id for item in evidence.items}
    unknown_ids = set(result.citations) - available_ids
    if unknown_ids:
        raise ValueError("引用不在当前任务证据包中：" + "、".join(sorted(unknown_ids)))


class TaskWorkOrderDraft(BaseModel):
    """用户报告的待审批草稿；字段合法不代表已确认故障或获准提交。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: ShortText
    revision: int = Field(default=1, ge=1)
    vehicle_id: ShortText
    symptom: LongText
    report_kind: Literal["user_report", "synthetic_user_report"]
    alert_code: ShortText | None = None
    dtc_codes: list[ShortText] = Field(default_factory=list, max_length=10)
    title: ShortText
    description: LongText
    status: Literal["pending_approval"] = "pending_approval"
