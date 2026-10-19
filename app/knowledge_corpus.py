"""按第二周语料清单加载带来源的知识片段。"""

import csv
import hashlib
import json
from pathlib import Path

from app.text_chunking import split_text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
MANIFEST_PATH = (
    PROJECT_ROOT / "evaluation" / "week2" / "corpus_manifest.csv"
)


def load_knowledge_chunks(
    documents_dir: Path = DOCUMENTS_DIR,
    manifest_path: Path = MANIFEST_PATH,
) -> list[dict]:
    documents_dir = Path(documents_dir)
    manifest_path = Path(manifest_path)
    chunks = []

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            # 只读取清单中明确纳入的资料。
            if row["week2_status"] != "include":
                continue

            document_id = row["document_id"]
            document_path = documents_dir / f"{document_id}.json"

            payload = json.loads(
                document_path.read_text(encoding="utf-8")
            )
            content = payload["content"]

            # 防止正文已变化，却仍使用旧清单。
            actual_hash = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            if actual_hash != row["content_sha256"]:
                raise ValueError(
                    f"资料正文与清单哈希不一致：{document_id}"
                )

            metadata = payload["metadata"]
            if metadata["document_id"] != document_id:
                raise ValueError(
                    f"资料 document_id 与清单不一致：{document_id}"
                )

            # 复用既有的 200 字、40 字重叠切片规则。
            for index, text in enumerate(split_text(content)):
                chunks.append({
                    "chunk_id": f"{document_id}:{index}",
                    "document_id": document_id,
                    "title": metadata["title"],
                    "source": metadata["source"],
                    "source_type": metadata["source_type"],
                    "chunk_index": index,
                    "text": text,
                })

    return chunks
