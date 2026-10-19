"""Run the isolated Week 2 vector-retrieval baseline.

The script verifies the frozen dataset before every run.  It uses only manifest
rows marked `include`; the Week 1 Chroma index is neither read nor modified.
"""

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval import CHUNK_OVERLAP, CHUNK_SIZE, split_text
from app.retrieval_eval import DEFAULT_KS, evaluate_rankings, find_gold_chunk_ids

WEEK2_DIR = PROJECT_ROOT / "evaluation" / "week2"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_questions(path: Path) -> List[Dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verify_freeze(freeze: Dict) -> None:
    for filename, expected_digest in freeze["files_sha256"].items():
        actual_digest = sha256(WEEK2_DIR / filename)
        if actual_digest != expected_digest:
            raise ValueError(
                f"冻结文件已变化：{filename} 的 SHA-256 为 {actual_digest}，"
                f"期望 {expected_digest}。请创建新数据版本，不要覆盖 week2-v1.0。"
            )


def load_chunks(manifest_path: Path) -> List[Dict]:
    chunks = []
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["week2_status"] != "include":
                continue

            document_path = PROJECT_ROOT / "data" / "documents" / f"{row['document_id']}.json"
            payload = load_json(document_path)
            content = payload["content"]
            if sha256_text(content) != row["content_sha256"]:
                raise ValueError(f"语料正文与清单哈希不一致：{row['document_id']}")

            for chunk_index, text in enumerate(split_text(content)):
                chunks.append(
                    {
                        "chunk_id": f"{row['document_id']}:{chunk_index}",
                        "document_id": row["document_id"],
                        "text": text,
                    }
                )

    if not chunks:
        raise ValueError("清单没有可纳入的评测片段")
    return chunks


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def percentile(values: List[float], percent: float):
    if not values:
        return None
    ordered = sorted(values)
    index = int(np.ceil(percent * len(ordered))) - 1
    return round(ordered[max(0, index)], 3)


def build_metadata(config: Dict, freeze: Dict, chunks: List[Dict], index_ms: float) -> Dict:
    return {
        "dataset_version": freeze["dataset_version"],
        "model": config["model"],
        "model_revision": config["model_revision"],
        "normalize_embeddings": config["normalize_embeddings"],
        "chunk_size_characters": CHUNK_SIZE,
        "chunk_overlap_characters": CHUNK_OVERLAP,
        "chunk_count": len(chunks),
        "document_count": len({chunk["document_id"] for chunk in chunks}),
        "index_build_ms": round(index_ms, 3),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "sentence_transformers_version": sentence_transformers.__version__,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=("development", "frozen_test"), default="development"
    )
    parser.add_argument(
        "--allow-frozen-test",
        action="store_true",
        help="明确允许运行已冻结的测试集。",
    )
    args = parser.parse_args()

    if args.split == "frozen_test" and not args.allow_frozen_test:
        parser.error("冻结测试集需要显式传入 --allow-frozen-test")

    config = load_json(WEEK2_DIR / "configs" / "vector_baseline.json")
    freeze = load_json(WEEK2_DIR / "freeze_manifest.json")
    splits = load_json(WEEK2_DIR / "splits.json")
    verify_freeze(freeze)

    questions = load_questions(WEEK2_DIR / "questions_draft.jsonl")
    split_key = "development_ids" if args.split == "development" else "frozen_test_ids"
    selected_ids = set(splits[split_key])
    selected_questions = [question for question in questions if question["id"] in selected_ids]
    if len(selected_questions) != len(selected_ids):
        raise ValueError("划分文件包含不存在的问题 ID")

    chunks = load_chunks(WEEK2_DIR / "corpus_manifest.csv")
    gold_by_question = find_gold_chunk_ids(selected_questions, chunks)

    started = time.perf_counter()
    model = SentenceTransformer(
        config["model"],
        revision=config["model_revision"],
        local_files_only=True,
    )
    chunk_embeddings = model.encode(
        [chunk["text"] for chunk in chunks],
        normalize_embeddings=config["normalize_embeddings"],
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    index_build_ms = (time.perf_counter() - started) * 1000

    index_dir = WEEK2_DIR / "indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        index_dir / "vector_baseline.npz",
        chunk_ids=np.array([chunk["chunk_id"] for chunk in chunks]),
        document_ids=np.array([chunk["document_id"] for chunk in chunks]),
        embeddings=chunk_embeddings,
    )

    rankings = {}
    query_latencies_ms = {}
    for question in selected_questions:
        started = time.perf_counter()
        query_embedding = model.encode(
            [question["question"]],
            normalize_embeddings=config["normalize_embeddings"],
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        scores = chunk_embeddings @ query_embedding
        order = np.argsort(-scores)
        rankings[question["id"]] = [chunks[index]["chunk_id"] for index in order]
        query_latencies_ms[question["id"]] = round(
            (time.perf_counter() - started) * 1000, 3
        )

    report = evaluate_rankings(selected_questions, rankings, gold_by_question, DEFAULT_KS)
    per_question = {item["id"]: item for item in report["positive_results"]}
    per_question.update({item["id"]: item for item in report["no_evidence_results"]})
    report["per_question"] = [
        {
            "id": question["id"],
            "question": question["question"],
            "answerable": question["answerable"],
            "query_latency_ms": query_latencies_ms[question["id"]],
            **per_question[question["id"]],
        }
        for question in selected_questions
    ]
    report.pop("positive_results")
    report.pop("no_evidence_results")
    report["run"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "retrieval_depth": len(chunks),
        "latency_ms": {
            "mean": round(sum(query_latencies_ms.values()) / len(query_latencies_ms), 3),
            "p50": percentile(list(query_latencies_ms.values()), 0.50),
            "p95": percentile(list(query_latencies_ms.values()), 0.95),
        },
        "metadata": build_metadata(config, freeze, chunks, index_build_ms),
    }

    results_dir = WEEK2_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"vector_baseline_{args.split}.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    metrics = report["metrics"]
    print(
        f"{args.split}: Recall@1={metrics['recall_at_1']:.3f}, "
        f"Recall@3={metrics['recall_at_3']:.3f}, Recall@5={metrics['recall_at_5']:.3f}, "
        f"MRR={metrics['mrr']:.3f}"
    )
    print(f"逐题结果与元数据：{output_path}")


if __name__ == "__main__":
    main()
