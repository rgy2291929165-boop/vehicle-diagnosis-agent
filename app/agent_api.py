"""第四周 Agent HTTP 入口：单次只读诊断与轻量存活检查。"""

from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.diagnosis_graph import build_diagnosis_graph
from app.diagnosis_input import make_diagnosis_state
from app.dtc_mcp_adapter import lookup_dtc_via_mcp

app = FastAPI(
    title="Vehicle Diagnosis Agent API",
    description="单次只读诊断。工具使用模拟数据，候选资料保留来源；无充分证据时不生成诊断建议。",
)


class DiagnosisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    vehicle_id: str | None = Field(default=None, max_length=100)
    symptom: str | None = Field(default=None, max_length=1000)
    dtc_codes: list[str] = Field(default_factory=list, max_length=1)
    requested_tool: Literal["lookup_dtc", "lookup_vehicle_history", "lookup_inventory"] = "lookup_dtc"
    part_number: str | None = Field(default=None, max_length=100)


class DiagnosisResponse(BaseModel):
    status: Literal["ok", "no_evidence", "needs_info", "stopped", "needs_human"]
    answer: str
    missing_fields: list[str]
    clarifying_question: str | None
    stop_reason: str | None
    citations: list[dict]
    tool_call_count: int
    trace: list[str]
    tool_trace: list[dict]
    handoff_request: dict | None
    tool_data_source: Literal["mock"] = "mock"


@lru_cache(maxsize=1)
def get_diagnosis_graph():
    return build_diagnosis_graph(dtc_lookup=lookup_dtc_via_mcp)


def get_knowledge_chunks() -> list[dict]:
    # 存活检查不需要导入向量库或 Embedding 相关依赖。
    from app.knowledge_corpus import load_knowledge_chunks

    try:
        return load_knowledge_chunks()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail={
            "reason": "corpus_unavailable",
            "message": "诊断资料库暂不可用，请检查资料文件与清单。",
        }) from error


@app.get("/health")
def health():
    """仅说明 HTTP 进程存活；不执行 MCP 查询或模型调用。"""
    return {"status": "ok"}


@app.post("/diagnose", response_model=DiagnosisResponse)
def diagnose(
    request: DiagnosisRequest,
    graph=Depends(get_diagnosis_graph),
    chunks: list[dict] = Depends(get_knowledge_chunks),
):
    # 请求模型只允许业务输入；每次重建预算和轨迹，不接收客户端状态覆盖。
    state = make_diagnosis_state(chunks, **request.model_dump())
    return graph.invoke(state)
