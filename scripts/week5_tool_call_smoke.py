"""一次真实模型工具调用烟测，记录结果，不生成最终诊断或工单。"""

import argparse
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from app.llm import DEFAULT_BASE_URL, DEFAULT_MODEL
from app.task_contracts import new_task_identity
from app.task_tool_calling import PROMPT_VERSION, SMOKE_QUESTION, TOOL_SPEC, run_tool_choice


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _json_hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def collect_versions():
    files = [
        "app/task_tool_calling.py", "app/task_contracts.py", "app/task_evidence.py",
        "scripts/week5_tool_call_smoke.py", "requirements-agent.lock.txt",
        "evaluation/week5/source_inventory.json",
    ]
    hashes = {}
    for name in files:
        path = PROJECT_ROOT / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    inventory = PROJECT_ROOT / "evaluation/week5/source_inventory.json"
    try:
        inventory_version = json.loads(inventory.read_text(encoding="utf-8")).get("inventory_version")
    except (OSError, ValueError, AttributeError):
        inventory_version = None
    return {
        "prompt": PROMPT_VERSION,
        "tool_schema_sha256": _json_hash(TOOL_SPEC),
        "file_sha256": hashes,
        "source_inventory_version": inventory_version,
        "python": platform.python_version(),
        "httpx": version("httpx"),
        "pydantic": version("pydantic"),
    }


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
        f"tool_call_smoke_{started:%Y%m%d_%H%M%S_%f}_{identity.task_id[-8:]}.json"
    )
    # 在模型请求前以独占方式创建文件，不能覆盖之前的运行证据。
    with path.open("x", encoding="utf-8") as handle:
        versions = collect_versions()
        result = run_tool_choice(
            SMOKE_QUESTION,
            model=os.getenv("DASHSCOPE_MODEL", DEFAULT_MODEL),
            base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
            api_key=api_key,
            task_id=identity.task_id,
        )
        passed = result["outcome"] == "tool_executed" and result["selected_topic"] == "CP_a054"
        record = {
            "started_at": started.isoformat(),
            "timezone": "Asia/Shanghai",
            "finished_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "scenario_data_kind": "synthetic_user_input",
            "source_data_kind": "local_reviewed_summary",
            "thread_id": identity.thread_id,
            "expected_topic": "CP_a054",
            "scenario_passed": passed,
            "versions": versions,
            "final_diagnosis_generated": False,
            "formal_work_order_written": False,
            **result,
        }
        serialized = json.dumps(record, ensure_ascii=False, indent=2)
        if api_key:
            serialized = serialized.replace(api_key, "[REDACTED]")
        handle.write(serialized + "\n")
    print("结果：", result["outcome"])
    print("模型选择主题：", result["selected_topic"] or "未知")
    print("实际模型请求尝试：", result["model_request_attempts"])
    print("只读工具执行尝试：", result["tool_execution_attempts"])
    print("场景检查：", "通过" if passed else "未通过，请保留记录排查")
    if result["reason"]:
        print("原因：", result["reason"])
    print("实际费用：未知")
    print("记录文件：", path.resolve())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
