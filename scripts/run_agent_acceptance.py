"""运行第三周 20 条工作流验收，保存节点更新和检查结果。"""

import argparse
from copy import deepcopy
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.diagnosis_graph import build_diagnosis_graph
from app.knowledge_corpus import load_knowledge_chunks
from scripts.run_diagnosis_demo import make_state


def execute_graph(graph, state):
    """当前图使用普通覆盖字段，逐个节点更新可重建最终状态。"""
    execution_input = deepcopy(state)
    run = {
        "input": deepcopy(state),
        "nodes": [],
        "output": deepcopy(state),
        "error": None,
    }
    try:
        for event in graph.stream(execution_input, stream_mode="updates"):
            for node, update in event.items():
                if not isinstance(update, dict):
                    raise RuntimeError(f"节点 {node} 返回了非字典更新")
                run["nodes"].append({
                    "node": node,
                    "update": deepcopy(update),
                })
                run["output"].update(deepcopy(update))
    except Exception as error:
        # 验收程序将异常记为失败，不将它当作正常终止。
        run["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    run["input_unchanged"] = execution_input == run["input"]
    return run


def check_run(case, run, data):
    actual = run["output"]
    initial = run["input"]
    gold = case["expect"]
    expected_path = data["paths"][gold["path"]]
    expected_nodes = [
        "check_diagnosis_information"
        if name == "check_information_completeness"
        else name
        for name in expected_path
    ]

    prior_trace = initial["tool_trace"]
    actual_trace = actual.get("tool_trace", [])
    new_trace = actual_trace[len(prior_trace):]
    if gold["status"] == "needs_info":
        expected_trace = []
    elif gold["status"] == "stopped":
        expected_trace = [{
            "tool_name": initial["requested_tool"],
            "status": "rejected",
            "reason": gold["stop_reason"],
        }]
    else:
        expected_trace = [{
            "tool_name": initial["requested_tool"],
            "status": "success",
        }]

    candidates = actual.get("retrieved_chunks", [])
    citations = actual.get("citations", [])
    originals = {
        item["chunk_id"]: item
        for item in initial["knowledge_chunks"]
    }
    expected_citations = [
        {
            "chunk_id": item.get("chunk_id"),
            "document_id": item.get("document_id"),
            "source": item.get("source"),
        }
        for item in candidates
    ]
    provenance_ok = all(
        item.get("chunk_id") in originals
        and all(
            item.get(field) == originals[item["chunk_id"]].get(field)
            for field in ("document_id", "source", "text")
        )
        for item in candidates
    )
    excerpts_ok = all(
        f'{item.get("text")} [来源: {item.get("chunk_id")}]'
        in actual.get("answer", "")
        for item in candidates
    )

    return {
        "execution_succeeded": run["error"] is None,
        "status": actual.get("status") == gold["status"],
        "tool_call_count": actual.get("tool_call_count") == gold["tool_call_count"],
        "citation_count": len(citations) == gold["citation_count"],
        "candidate_count": len(candidates) == gold["citation_count"],
        "trace": actual.get("trace") == expected_path,
        "node_order": [item["node"] for item in run["nodes"]] == expected_nodes,
        "missing_fields": actual.get("missing_fields") == gold.get("missing_fields", []),
        "stop_reason": actual.get("stop_reason") == gold.get("stop_reason"),
        "tool_trace_preserved": actual_trace[:len(prior_trace)] == prior_trace,
        "new_tool_trace": new_trace == expected_trace,
        "citations_match_candidates": citations == expected_citations,
        "candidate_provenance": provenance_ok,
        "answer_contains_cited_text": excerpts_ok,
        "input_unchanged": run["input_unchanged"],
    }


def execute_case(case, graph, data, real_chunks):
    corpus = (
        real_chunks
        if case["corpus"] == "real"
        else data["corpora"][case["corpus"]]
    )
    state = make_state(deepcopy(corpus), **deepcopy(case["input"]))
    seed = None

    if case.get("mode") == "repeat":
        seed = execute_graph(graph, state)
        if seed["error"] is None:
            state = make_state(deepcopy(corpus), **deepcopy(case["input"]))
            for field in (
                "tool_call_count",
                "seen_tool_calls",
                "tool_trace",
                "retrieval_query",
                "retrieved_chunks",
                "citations",
            ):
                state[field] = deepcopy(seed["output"][field])
            run = execute_graph(graph, state)
        else:
            run = seed
    else:
        run = execute_graph(graph, state)

    checks = check_run(case, run, data)
    if seed is not None:
        checks["repeat_seed_succeeded"] = (
            seed["error"] is None
            and seed["output"].get("status") == "ok"
            and seed["output"].get("tool_call_count")
            == seed["input"]["tool_call_count"] + 1
            and seed["input_unchanged"]
        )

    return {
        "case_id": case["id"],
        "label": case["label"],
        "corpus": case["corpus"],
        "mode": case.get("mode", "once"),
        "expect": deepcopy(case["expect"]),
        "seed": seed,
        "run": run,
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def sha256_json(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path,
        default=PROJECT_ROOT / "evaluation/week3/agent_cases.json",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "evaluation/week3",
    )
    args = parser.parse_args(argv)
    cases_bytes = args.cases.read_bytes()
    data = json.loads(cases_bytes.decode("utf-8"))
    cases = data["cases"]
    if len(cases) != 20 or len({case["id"] for case in cases}) != 20:
        raise ValueError("当前验收要求 20 条案例，且 ID 必须唯一")
    for case in cases:
        if case["corpus"] != "real" and case["corpus"] not in data["corpora"]:
            raise ValueError(f'{case["id"]} 指向未知资料组')
        if case["expect"]["path"] not in data["paths"]:
            raise ValueError(f'{case["id"]} 指向未知节点路径')
        if case.get("mode", "once") not in ("once", "repeat"):
            raise ValueError(f'{case["id"]} 使用了未知执行模式')

    real_chunks = load_knowledge_chunks()
    graph = build_diagnosis_graph()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trajectories_path = args.output_dir / "agent_trajectories.jsonl"
    records = []

    with trajectories_path.open("w", encoding="utf-8") as handle:
        for case in cases:
            record = execute_case(case, graph, data, real_chunks)
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            label = "PASS" if record["passed"] else "FAIL"
            print(f'[{label}] {case["id"]} {case["label"]}')
            if not record["passed"]:
                print("  未通过检查：", ", ".join(record["failed_checks"]))
                if record["run"]["error"]:
                    print("  异常：", record["run"]["error"])

    app_dir = Path(load_knowledge_chunks.__code__.co_filename).resolve().parent
    code_files = [
        "diagnosis_graph.py", "diagnosis_state.py", "diagnostic_tools.py",
        "tool_guard.py", "tool_planner.py", "tool_router.py",
        "knowledge_retrieval.py", "knowledge_corpus.py", "bm25.py", "retrieval.py",
    ]
    passed = sum(record["passed"] for record in records)
    groups = {}
    for group, is_real in (("real_corpus_input", True), ("fixture_corpus_input", False)):
        subset = [
            record for record in records
            if (record["corpus"] == "real") == is_real
        ]
        groups[group] = {
            "total": len(subset),
            "passed": sum(record["passed"] for record in subset),
        }
    summary = {
        "version": data["version"],
        "scope": "模拟工具、候选检索、引用与工作流控制；不评估实车诊断正确率",
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "failed_cases": [
            {"id": record["case_id"], "checks": record["failed_checks"]}
            for record in records if not record["passed"]
        ],
        "corpus_groups": groups,
        "real_documents": len({item["document_id"] for item in real_chunks}),
        "real_chunks": len(real_chunks),
        "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "real_corpus_sha256": sha256_json(real_chunks),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "code_sha256": {
            name: hashlib.sha256((app_dir / name).read_bytes()).hexdigest()
            for name in code_files
        },
        "environment": {
            "python": platform.python_version(),
            "langgraph": version("langgraph"),
        },
        "trajectories_file": trajectories_path.name,
    }
    summary_path = args.output_dir / "agent_acceptance_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n验收结果：{passed}/{len(records)} 通过")
    print("轨迹文件：", trajectories_path)
    print("汇总文件：", summary_path)
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
