"""Evaluate RRF fusion from the reproducible Week 2 base-retriever rankings."""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hybrid_retrieval import reciprocal_rank_fusion
from app.retrieval_eval import DEFAULT_KS, evaluate_rankings

WEEK2_DIR = PROJECT_ROOT / "evaluation" / "week2"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def load_questions(split: str, splits: Dict) -> List[Dict]:
    questions = [
        json.loads(line)
        for line in (WEEK2_DIR / "questions_draft.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    split_key = "development_ids" if split == "development" else "frozen_test_ids"
    selected_ids = set(splits[split_key])
    selected_questions = [question for question in questions if question["id"] in selected_ids]
    if len(selected_questions) != len(selected_ids):
        raise ValueError("划分文件包含不存在的问题 ID")
    return selected_questions


def result_rows_by_id(path: Path, split: str, dataset_version: str) -> Dict[str, Dict]:
    report = load_json(path)
    run = report.get("run", {})
    if run.get("split") != split:
        raise ValueError(f"基线结果划分不匹配：{path}")
    if run.get("metadata", {}).get("dataset_version") != dataset_version:
        raise ValueError(f"基线结果数据版本不匹配：{path}")

    rows = report.get("per_question", [])
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError(f"基线结果包含重复问题 ID：{path}")
    return by_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=("development", "frozen_test"), default="development"
    )
    parser.add_argument("--allow-frozen-test", action="store_true")
    args = parser.parse_args()
    if args.split == "frozen_test" and not args.allow_frozen_test:
        parser.error("冻结测试集需要显式传入 --allow-frozen-test")

    config_path = WEEK2_DIR / "configs" / "hybrid_rrf.json"
    config = load_json(config_path)
    freeze = load_json(WEEK2_DIR / "freeze_manifest.json")
    splits = load_json(WEEK2_DIR / "splits.json")
    verify_freeze(freeze)

    vector_path = WEEK2_DIR / "results" / f"vector_baseline_{args.split}.json"
    bm25_path = WEEK2_DIR / "results" / f"bm25_{args.split}.json"
    if not vector_path.exists() or not bm25_path.exists():
        raise FileNotFoundError("请先生成同一划分的向量和 BM25 基线结果")

    questions = load_questions(args.split, splits)
    expected_ids = {question["id"] for question in questions}
    vector_rows = result_rows_by_id(vector_path, args.split, freeze["dataset_version"])
    bm25_rows = result_rows_by_id(bm25_path, args.split, freeze["dataset_version"])
    if set(vector_rows) != expected_ids or set(bm25_rows) != expected_ids:
        raise ValueError("基线结果的问题集合与当前划分不一致")

    rankings = {}
    latencies_ms = {}
    for question in questions:
        question_id = question["id"]
        vector_ranking = vector_rows[question_id]["ranked_chunk_ids"]
        bm25_ranking = bm25_rows[question_id]["ranked_chunk_ids"]
        started = time.perf_counter()
        rankings[question_id] = reciprocal_rank_fusion(
            {"vector": vector_ranking, "bm25": bm25_ranking},
            k=config["k"],
            weights=config["weights"],
        )
        latencies_ms[question_id] = round((time.perf_counter() - started) * 1000, 3)

    gold_by_question = {
        question_id: set(vector_rows[question_id].get("gold_chunk_ids", []))
        for question_id in expected_ids
    }
    report = evaluate_rankings(questions, rankings, gold_by_question, DEFAULT_KS)
    results_by_id = {item["id"]: item for item in report["positive_results"]}
    results_by_id.update({item["id"]: item for item in report["no_evidence_results"]})
    report["per_question"] = [
        {
            "id": question["id"],
            "question": question["question"],
            "answerable": question["answerable"],
            "fusion_latency_ms": latencies_ms[question["id"]],
            **results_by_id[question["id"]],
        }
        for question in questions
    ]
    report.pop("positive_results")
    report.pop("no_evidence_results")
    report["run"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "retrieval_depth": len(rankings[questions[0]["id"]]),
        "latency_ms": {
            "mean": round(sum(latencies_ms.values()) / len(latencies_ms), 3),
            "p50": percentile(list(latencies_ms.values()), 0.50),
            "p95": percentile(list(latencies_ms.values()), 0.95),
        },
        "metadata": {
            "dataset_version": freeze["dataset_version"],
            "fusion": config["fusion"],
            "k": config["k"],
            "weights": config["weights"],
            "config_sha256": sha256_bytes(config_path),
            "vector_result_sha256": sha256_bytes(vector_path),
            "bm25_result_sha256": sha256_bytes(bm25_path),
            "latency_scope": "仅 RRF 融合；基线检索耗时见各自结果文件",
        },
    }

    output_path = WEEK2_DIR / "results" / f"hybrid_rrf_{args.split}.json"
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
