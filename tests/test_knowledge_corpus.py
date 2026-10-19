import csv
import hashlib
import json

import pytest

from app.knowledge_corpus import load_knowledge_chunks


def make_corpus(tmp_path, content="P0AA6 绝缘 故障 检查", status="include"):
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()

    payload = {
        "metadata": {
            "document_id": "demo",
            "title": "测试资料",
            "source": "tests/demo.txt",
            "source_type": "manual_text",
        },
        "content": content,
    }

    (documents_dir / "demo.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "corpus_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "document_id",
                "week2_status",
                "content_sha256",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "document_id": "demo",
            "week2_status": status,
            "content_sha256": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
        })

    return documents_dir, manifest_path


def test_loader_only_reads_included_documents_and_preserves_sources(tmp_path):
    documents_dir, manifest_path = make_corpus(tmp_path)

    # 不在清单中的文件不能被加载，甚至不应尝试解析。
    (documents_dir / "unlisted.json").write_text(
        "不是有效 JSON",
        encoding="utf-8",
    )

    # 排除项即使文件不存在，也不应尝试读取。
    with manifest_path.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow([
            "excluded",
            "exclude_legacy_demo",
            "unused-hash",
        ])

    chunks = load_knowledge_chunks(documents_dir, manifest_path)

    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "demo:0"
    assert chunks[0]["document_id"] == "demo"
    assert chunks[0]["title"] == "测试资料"
    assert chunks[0]["source"] == "tests/demo.txt"
    assert chunks[0]["text"] == "P0AA6 绝缘 故障 检查"


def test_loader_splits_long_documents_with_stable_chunk_ids(tmp_path):
    content = "".join(chr(0x4E00 + index) for index in range(300))
    documents_dir, manifest_path = make_corpus(tmp_path, content=content)

    chunks = load_knowledge_chunks(documents_dir, manifest_path)

    assert [item["chunk_id"] for item in chunks] == [
        "demo:0",
        "demo:1",
    ]
    assert len(chunks[0]["text"]) == 200
    assert len(chunks[1]["text"]) == 140
    assert chunks[0]["text"][-40:] == chunks[1]["text"][:40]
    assert all(item["source"] == "tests/demo.txt" for item in chunks)


def test_loader_rejects_content_that_does_not_match_manifest_hash(tmp_path):
    documents_dir, manifest_path = make_corpus(tmp_path)
    document_path = documents_dir / "demo.json"

    payload = json.loads(document_path.read_text(encoding="utf-8"))
    payload["content"] = "正文被修改了"
    document_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="哈希"):
        load_knowledge_chunks(documents_dir, manifest_path)


def test_loader_returns_empty_when_no_documents_are_included(tmp_path):
    documents_dir, manifest_path = make_corpus(
        tmp_path,
        status="exclude_legacy_demo",
    )

    assert load_knowledge_chunks(documents_dir, manifest_path) == []


def test_real_corpus_loads_without_vector_or_model_dependencies():
    import os
    from pathlib import Path
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from app.knowledge_corpus import load_knowledge_chunks
chunks = load_knowledge_chunks()
assert len(chunks) == 16
assert len({chunk['document_id'] for chunk in chunks}) == 12
assert not {'chromadb', 'sentence_transformers', 'torch', 'app.retrieval'} & sys.modules.keys()
"""],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
