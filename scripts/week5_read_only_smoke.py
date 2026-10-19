"""一次两阶段只读烟测：工具选择、查询、JSON解释与引用检查。"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.llm import DEFAULT_BASE_URL, DEFAULT_MODEL
from app.task_contracts import new_task_identity
from app.task_read_only import (
    ANSWER_PROMPT_VERSION, ModelReadOnlyAnswer, READ_ONLY_QUESTION, run_read_only_task,
)
from scripts.week5_tool_call_smoke import collect_versions


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "evaluation/week5/day04",
    )
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    identity = new_task_identity()
    started = datetime.now(ZoneInfo("Asia/Shanghai"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / (
        f"read_only_smoke_{started:%Y%m%d_%H%M%S_%f}_{identity.task_id[-8:]}.json"
    )
    with path.open("x", encoding="utf-8") as handle:
        versions = collect_versions()
        versions["answer_prompt"] = ANSWER_PROMPT_VERSION
        versions["answer_schema_sha256"] = hashlib.sha256(
            json.dumps(ModelReadOnlyAnswer.model_json_schema(), sort_keys=True).encode()
        ).hexdigest()
        for name in ("app/task_read_only.py", "scripts/week5_read_only_smoke.py"):
            versions["file_sha256"][name] = hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
        result = run_read_only_task(
            READ_ONLY_QUESTION,
            model=os.getenv("DASHSCOPE_MODEL", DEFAULT_MODEL),
            base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
            api_key=api_key, task_id=identity.task_id,
        )
        passed = (
            result["outcome"] == "answer_validated" and result["selected_topic"] == "CP_a054"
            and result["model_request_attempts"] <= 2 and result["tool_execution_attempts"] == 1
        )
        record = {
            "started_at": started.isoformat(), "timezone": "Asia/Shanghai",
            "finished_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "scenario_data_kind": "synthetic_user_input",
            "source_data_kind": "local_reviewed_summary",
            "thread_id": identity.thread_id,
            "expected_topic": "CP_a054",
            "scenario_structure_passed": passed,
            "versions": versions,
            "formal_work_order_written": False,
            **result,
        }
        serialized = json.dumps(record, ensure_ascii=False, indent=2)
        if api_key:
            serialized = serialized.replace(api_key, "[REDACTED]")
        handle.write(serialized + "\n")
    print("结果：", result["outcome"])
    print("实际模型请求尝试：", result["model_request_attempts"])
    print("只读工具执行尝试：", result["tool_execution_attempts"])
    print("结构与引用检查：", "通过，语义待核对" if passed else "未通过，请保留记录排查")
    print("回答：", result["final_result"]["message"])
    print("引用：", result["final_result"]["citations"])
    if result["reason"]:
        print("原因：", result["reason"])
    print("Token 总量：", result["usage_total"] if result["usage_total"] is not None else "未知（已知部分见记录）")
    print("实际费用：未知")
    print("记录文件：", path.resolve())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
