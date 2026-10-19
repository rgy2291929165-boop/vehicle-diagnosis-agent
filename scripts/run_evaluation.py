import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = PROJECT_ROOT / "evaluation" / "questions.json"
RESULTS_PATH = PROJECT_ROOT / "evaluation" / "results.json"
API_URL = "http://127.0.0.1:8000/chat"


def check_result(question, status_code, body):
    expected_status = question["expected_status"]
    citations = body.get("citations", [])
    sources = {citation.get("source") for citation in citations}

    if status_code != 200:
        return False, f"HTTP {status_code}"

    if body.get("status") != expected_status:
        return False, f'状态为 {body.get("status")}，期望 {expected_status}'

    if expected_status == "ok":
        if not body.get("answer"):
            return False, "缺少回答"

        if not citations:
            return False, "缺少引用"

        if not any(
            source in sources
            for source in question["expected_sources"]
        ):
            return False, f"引用来源不符合预期：{sorted(sources)}"

        return True, "通过"

    if citations:
        return False, "无证据问题不应返回引用"

    if "没有足够证据" not in body.get("answer", ""):
        return False, "无证据回答缺少安全提示"

    return True, "通过"


def main():
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []

    with httpx.Client(timeout=40.0, trust_env=False) as client:
        for question in questions:
            started_at = time.perf_counter()

            try:
                response = client.post(
                    API_URL,
                    json={"question": question["question"]},
                )
                elapsed_ms = round((time.perf_counter() - started_at) * 1000)

                try:
                    body = response.json()
                except ValueError:
                    body = {"raw_response": response.text}

                passed, reason = check_result(
                    question,
                    response.status_code,
                    body,
                )
            except httpx.HTTPError as error:
                elapsed_ms = round((time.perf_counter() - started_at) * 1000)
                body = {}
                passed = False
                reason = f"请求失败：{error}"

            results.append(
                {
                    "id": question["id"],
                    "question": question["question"],
                    "expected_status": question["expected_status"],
                    "expected_sources": question["expected_sources"],
                    "actual_status_code": response.status_code if "response" in locals() else None,
                    "actual_status": body.get("status"),
                    "citations": body.get("citations", []),
                    "answer": body.get("answer", body.get("detail", "")),
                    "elapsed_ms": elapsed_ms,
                    "passed": passed,
                    "reason": reason,
                }
            )

            print(f'{question["id"]}: {"PASS" if passed else "FAIL"} - {reason}')

    RESULTS_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    passed_count = sum(result["passed"] for result in results)
    print(f"\n验收完成：{passed_count}/{len(results)} 通过")
    print(f"结果已保存：{RESULTS_PATH}")

    if passed_count != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()