import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import (
    ModelConfigurationError,
    ModelEmptyResponseError,
    ModelRequestError,
    ModelTimeoutError,
    generate_answer,
)
from app.retrieval import index_documents, search_documents

app = FastAPI(title="Vehicle Diagnosis Agent")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

MAX_EVIDENCE_DISTANCE = 1.1


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class Citation(BaseModel):
    source: str
    chunk_id: str
    title: str
    document_id: str


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    status: str


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    source: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    source_type: str = Field(default="manual_text")


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    source: str
    source_type: str
    imported_at: datetime
    char_count: int


class IndexResponse(BaseModel):
    document_count: int
    chunk_count: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=5)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source: str
    source_type: str
    chunk_index: int
    text: str
    distance: float


class SearchResponse(BaseModel):
    results: List[SearchResult]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    search_results = search_documents(request.question, top_k=3)
    evidence = [
        result
        for result in search_results
        if result["distance"] <= MAX_EVIDENCE_DISTANCE
    ]

    if not evidence:
        return ChatResponse(
            answer="资料库中没有足够证据，无法提供具体维修步骤。",
            citations=[],
            status="no_evidence",
        )

    try:
        answer = generate_answer(request.question, evidence)
    except ModelConfigurationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except ModelTimeoutError as error:
        raise HTTPException(status_code=504, detail="模型响应超时，请稍后重试。") from error
    except ModelEmptyResponseError as error:
        raise HTTPException(status_code=502, detail="模型未返回有效内容，请稍后重试。") from error
    except ModelRequestError as error:
        raise HTTPException(status_code=502, detail="模型服务请求失败，请稍后重试。") from error
    if answer == "NO_EVIDENCE":
        return ChatResponse(
            answer="资料库中没有足够证据，无法提供具体维修步骤。",
            citations=[],
            status="no_evidence",
        )
    
    citations = [
        Citation(
            source=result["source"],
            chunk_id=result["chunk_id"],
            title=result["title"],
            document_id=result["document_id"],
        )
        for result in evidence
    ]

    return ChatResponse(
        answer=answer,
        citations=citations,
        status="ok",
    )


@app.post("/documents", response_model=DocumentResponse, status_code=201)
def create_document(document: DocumentCreate):
    saved_document = DocumentResponse(
        document_id=str(uuid4()),
        title=document.title,
        source=document.source,
        source_type=document.source_type,
        imported_at=datetime.now(timezone.utc),
        char_count=len(document.content),
    )

    document_path = DOCUMENTS_DIR / f"{saved_document.document_id}.json"
    document_path.write_text(
        json.dumps(
            {
                "metadata": saved_document.model_dump(mode="json"),
                "content": document.content,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return saved_document


@app.get("/documents", response_model=List[DocumentResponse])
def list_documents():
    documents = []

    for document_path in DOCUMENTS_DIR.glob("*.json"):
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        documents.append(DocumentResponse(**payload["metadata"]))

    return documents


@app.post("/index", response_model=IndexResponse)
def build_index():
    return index_documents()


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest):
    return SearchResponse(
        results=search_documents(
            query=request.query,
            top_k=request.top_k,
        )
    )