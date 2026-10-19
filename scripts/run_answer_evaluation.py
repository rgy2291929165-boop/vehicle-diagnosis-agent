"""Generate and record the Week 2 development answer-quality review set."""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_eval import evaluate_answer, order_contiguous_contexts
from app.bm25 import BM25Retriever
from app.llm import ANSWER_PROMPT_VERSION, generate_answer
from app.retrieval import split_text
from app.retrieval_eval import find_gold_chunk_ids

WEEK2_DIR = PROJECT_ROOT / "evaluation" / "week2"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(freeze: Dict) -> None:
    for filename, expected_digest in freeze["files_sha256"].items():
        if sha256_bytes(WEEK2_DIR / filename) != expected_digest:
            raise ValueError(f"冻结文件已变化：{filename} 的 SHA-256 不匹配")


def load_questions() -> List[Dict]:
    return [
        json.loads(line)
        for line in (WEEK2_DIR / "questions_draft.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def load_chunks() -> List[Dict]:
    import csv

    chunks = []
    manifest_path = WEEK2_DIR / "corpus_manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["week2_status"] != "include":
                continue
            document_path = PROJECT_ROOT / "data" / "documents" / f"{row['document_id']}.json"
            payload = load_json(document_path)
            content = payload["content"]
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != row["content_sha256"]:
                raise ValueError(f"语料正文与清单哈希不一致：{row['document_id']}")
            for index, text in enumerate(split_text(content)):
                chunks.append(
                    {
                        "chunk_id": f"{row['document_id']}:{index}",
                        "document_id": row["document_id"],
                        "title": payload["metadata"]["title"],
                        "source": payload["metadata"]["source"],
                        "text": text,
                    }
                )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split", choices=("development", "frozen_test"), default="development"
    )
    parser.add_argument("--allow-frozen-test", action="store_true")
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="只重新核验已有回答，不再次调用模型服务。",
    )
    parser.add_argument(
        "--output-name",
        default="answer_evaluation_development_prompt_v4",
        help="结果文件名，不含 .json；用于保留不同提示词版本的对照结果。",
    )
    args = parser.parse_args()
    if args.split == "frozen_test" and not args.allow_frozen_test:
        parser.error("冻结测试集需要显式传入 --allow-frozen-test")
    if Path(args.output_name).name != args.output_name or not args.output_name:
        parser.error("--output-name 只能是文件名，不能包含目录")

    config_path = WEEK2_DIR / "configs" / "answer_evaluation_development.json"
    config = load_json(config_path)
    if args.split != config["split"]:
        raise ValueError("当前回答评测配置只定义了 development 抽样题")

    freeze = load_json(WEEK2_DIR / "freeze_manifest.json")
    splits = load_json(WEEK2_DIR / "splits.json")
    verify_freeze(freeze)
    questions_by_id = {question["id"]: question for question in load_questions()}
    selected_questions = [questions_by_id[question_id] for question_id in config["question_ids"]]
    development_ids = set(splits["development_ids"])
    if not set(config["question_ids"]).issubset(development_ids):
        raise ValueError("回答评测题目必须全部来自开发集")

    chunks = load_chunks()
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    gold_by_question = find_gold_chunk_ids(selected_questions, chunks)
    retriever = BM25Retriever().fit(chunks)
    output_path = WEEK2_DIR / "results" / f"{args.output_name}.json"
    existing_by_id = {}
    if args.reuse_existing:
        if not output_path.exists():
            raise FileNotFoundError("没有可重新核验的回答评测结果")
        existing = load_json(output_path)
        existing_by_id = {row["id"]: row for row in existing["results"]}
        if set(existing_by_id) != set(config["question_ids"]):
            raise ValueError("已有回答结果与当前评测配置不一致")

    results = []
    for question in selected_questions:
        ranked_chunk_ids = retriever.rank(question["question"])
        retrieval_ranked_chunk_ids = ranked_chunk_ids[: config["retrieval_depth"]]
        retrieved_chunk_ids = order_contiguous_contexts(retrieval_ranked_chunk_ids)
        if args.reuse_existing:
            existing_row = existing_by_id[question["id"]]
            raw_answer = existing_row["answer"]
            elapsed_ms = existing_row["elapsed_ms"]
            retrieved_chunk_ids = existing_row["retrieved_chunk_ids"]
            retrieval_ranked_chunk_ids = existing_row.get(
                "retrieval_ranked_chunk_ids", retrieved_chunk_ids
            )
            contexts = [chunks_by_id[chunk_id] for chunk_id in retrieved_chunk_ids]
        else:
            contexts = [chunks_by_id[chunk_id] for chunk_id in retrieved_chunk_ids]
            started = time.perf_counter()
            raw_answer = generate_answer(question["question"], contexts)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        result = evaluate_answer(
            question,
            raw_answer,
            gold_by_question[question["id"]],
            retrieved_chunk_ids,
        )
        results.append(
            {
                "id": question["id"],
                "question": question["question"],
                "answerable": question["answerable"],
                "answer": raw_answer,
                "elapsed_ms": elapsed_ms,
                "retrieval_ranked_chunk_ids": retrieval_ranked_chunk_ids,
                "retrieved_chunks": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "text": chunk["text"],
                    }
                    for chunk in contexts
                ],
                **result,
            }
        )

    output = {
        "run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "split": args.split,
            "dataset_version": freeze["dataset_version"],
            "retriever": config["retriever"],
            "retrieval_depth": config["retrieval_depth"],
            "config_sha256": sha256_bytes(config_path),
            "model": os.getenv("DASHSCOPE_MODEL", "qwen3.7-flash"),
            "answer_prompt_version": ANSWER_PROMPT_VERSION,
        },
        "rubric": config["rubric"],
        "results": results,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    action = "已重新核验" if args.reuse_existing else "已生成"
    print(f"{action} {len(results)} 道开发集回答：{output_path}")
    print("请人工填写 unsupported_claim，并复核引用是否支撑每项关键主张。")


if __name__ == "__main__":
    main()
