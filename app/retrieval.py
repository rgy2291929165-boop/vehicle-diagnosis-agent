import json
from pathlib import Path
from typing import Dict, List

import chromadb
from sentence_transformers import SentenceTransformer

from app.text_chunking import CHUNK_SIZE, CHUNK_OVERLAP, split_text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"

COLLECTION_NAME = "vehicle_documents"

_embedding_model = None


def get_embedding_model():
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

    return _embedding_model


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_embedding_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name=COLLECTION_NAME)


def index_documents() -> Dict[str, int]:
    collection = get_collection()
    existing = collection.get()

    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    ids = []
    texts = []
    metadatas = []
    document_count = 0

    for document_path in DOCUMENTS_DIR.glob("*.json"):
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        metadata = payload["metadata"]

        if metadata["source_type"] == "test":
            continue

        chunks = split_text(payload["content"])

        if not chunks:
            continue

        document_count += 1

        for chunk_index, chunk_text in enumerate(chunks):
            ids.append(f'{metadata["document_id"]}:{chunk_index}')
            texts.append(chunk_text)
            metadatas.append(
                {
                    "document_id": metadata["document_id"],
                    "title": metadata["title"],
                    "source": metadata["source"],
                    "source_type": metadata["source_type"],
                    "chunk_index": chunk_index,
                }
            )

    if texts:
        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embed_texts(texts),
        )

    return {
        "document_count": document_count,
        "chunk_count": len(texts),
    }


def search_documents(query: str, top_k: int) -> List[Dict]:
    collection = get_collection()
    total_chunks = collection.count()

    if total_chunks == 0:
        return []

    result = collection.query(
        query_embeddings=[embed_texts([query])[0]],
        n_results=min(top_k, total_chunks),
        include=["documents", "metadatas", "distances"],
    )

    results = []

    for chunk_id, text, metadata, distance in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        results.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "distance": distance,
                **metadata,
            }
        )

    return results