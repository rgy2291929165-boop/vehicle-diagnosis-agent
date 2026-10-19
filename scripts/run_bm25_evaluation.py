"""Run the isolated BM25 baseline against the frozen Week 2 dataset."""

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bm25 import BM25Retriever, TOKENIZER_NAME
from app.retrieval import CHUNK_OVERLAP, CHUNK_SIZE, split_text
from app.retrieval_eval import DEFAULT_KS, evaluate_rankings, find_gold_chunk_ids

WEEK2_DIR = PROJECT_ROOT / "evaluation" / "week2"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def percentile(values: List[float], percent: float):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, int((len(ordered) * percent + 0.999999)) - 1)
    return round(ordered[index], 3)


def verify_freeze(freeze: Dict) -> None:
    for filename, expected_digest in freeze["files_sha256"].items():
        actual_digest = sha256_bytes(WEEK2_DIR / filename)
        if actual_digest != expected_digest:
            raise ValueError(
                f"冻结文件已变化：{filename} 的 SHA-256 不匹配。"
                "请创建新数据版本，不要覆盖 week2-v1.0。"
            )


def load_chunks() -> List[Dict]:
    chunks = []
    manifest_path = WEEK2_DIR / "corpus_manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["week2_status"] != "include":
                continue
            path = PROJECT_ROOT / "data" / "documents" / f"{row['document_id']}.json"
            payload = load_json(path)
            if sha256_text(payload["content"]) != row["content_sha256"]:
                raise ValueError(f"语料正文与清单哈希不一致：{row['document_id']}")
            chunks.extend(
                {
                    "chunk_id": f"{row['document_id']}:{index}",
                    "document_id": row["document_id"],
                    "text": text,
                }
                for index, text in enumerate(split_text(payload["content"]))
            )
    if not chunks:
        raise ValueError("清单没有可纳入的评测片段")
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=("development", "frozen_test"), default="development"
    )
    parser.add_argument("--allow-frozen-test", action="store_true")
    args = parser.parse_args()
    if args.split == "frozen_test" and not args.allow_frozen_test:
        parser.error("冻结测试集需要显式传入 --allow-frozen-test")

    config_path = WEEK2_DIR / "configs" / "bm25_baseline.json"
    config = load_json(config_path)
    freeze = load_json(WEEK2_DIR / "freeze_manifest.json")
    splits = load_json(WEEK2_DIR / "splits.json")
    verify_freeze(freeze)

    questions = [
        json.loads(line)
        for line in (WEEK2_DIR / "questions_draft.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    split_key = "development_ids" if args.split == "development" else "frozen_test_ids"
    selected_ids = set(splits[split_key])
    selected_questions = [question for question in questions if question["id"] in selected_ids]
    if len(selected_questions) != len(selected_ids):
        raise ValueError("划分文件包含不存在的问题 ID")

    chunks = load_chunks()
    gold_by_question = find_gold_chunk_ids(selected_questions, chunks)
    started = time.perf_counter()
    retriever = BM25Retriever(k1=config["k1"], b=config["b"]).fit(chunks)
    index_build_ms = (time.perf_counter() - started) * 1000

    rankings = {}
    query_latencies_ms = {}
    for question in selected_questions:
        started = time.perf_counter()
        rankings[question["id"]] = retriever.rank(question["question"])
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
        "metadata": {
            "dataset_version": freeze["dataset_version"],
            "k1": config["k1"],
            "b": config["b"],
            "tokenizer": TOKENIZER_NAME,
            "chunk_size_characters": CHUNK_SIZE,
            "chunk_overlap_characters": CHUNK_OVERLAP,
            "chunk_count": len(chunks),
            "document_count": len({chunk["document_id"] for chunk in chunks}),
            "index_build_ms": round(index_build_ms, 3),
            "config_sha256": sha256_bytes(config_path),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    results_dir = WEEK2_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"bm25_{args.split}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metrics = report["metrics"]
    print(
        f"{args.split}: Recall@1={metrics['recall_at_1']:.3f}, "
        f"Recall@3={metrics['recall_at_3']:.3f}, Recall@5={metrics['recall_at_5']:.3f}, "
        f"MRR={metrics['mrr']:.3f}"
    )
    print(f"逐题结果与元数据：{output_path}")


if __name__ == "__main__":
    main()
