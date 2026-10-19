"""第四周本地阶段演示：隔离数据库、显式审批与可复查证据。"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.checkpoint.sqlite import SqliteSaver

from app.diagnosis_graph import build_diagnosis_graph
from app.diagnosis_input import make_diagnosis_state
from app.dtc_mcp_adapter import lookup_dtc_via_mcp
from app.knowledge_corpus import load_knowledge_chunks
from app.work_order_graph import build_work_order_graph


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path,
                        default=PROJECT_ROOT / "evaluation/week4/demo-runs")
    parser.add_argument("--base-url", help="可选：验证已启动的只读 HTTP 服务")
    parser.add_argument("--scripted-review", action="store_true",
                        help="显式使用教学预设批准；不代表真人审批")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = args.output_root.expanduser().resolve() / run_id
    output.mkdir(parents=True)
    diagnosis_db = output / "diagnosis.sqlite"
    review_db = output / "review.sqlite"
    orders_db = output / "orders.sqlite"
    summary = {"run_id": run_id, "status": "running", "checks": {},
               "scope": "固定教学车辆、模拟只读工具和隔离本地演示工单",
               "review_mode": "scripted_fixture" if args.scripted_review else "interactive",
               "github_ci": "deferred_not_executed"}
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    sequence = 0

    def command(script, *arguments):
        nonlocal sequence
        sequence += 1
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / script), *map(str, arguments)],
            cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True, timeout=60,
        )
        (output / f"{sequence:02d}-{Path(script).stem}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8")
        require(result.returncode == 0, f"{script} 失败，见第 {sequence} 份日志")

    def snapshot(factory, database, thread):
        with SqliteSaver.from_conn_string(str(database)) as saver:
            return factory(saver).get_state({"configurable": {"thread_id": thread}})

    def passed(name, detail):
        summary["checks"][name] = detail
        print(f"[PASS] {detail}", flush=True)

    def orders():
        require(orders_db.exists(), "演示工单库尚未创建")
        with closing(sqlite3.connect(orders_db)) as connection:
            return connection.execute(
                "SELECT work_order_id, idempotency_key, approved_draft_json FROM work_orders"
            ).fetchall()

    try:
        print("第四周阶段演示；全部工单仅写入本次独立目录：", output, flush=True)
        thread = "stage-diagnosis"
        for action, extra, expected_status, expected_count in [
            ("start", [], "needs_info", 0),
            ("continue", ["--dtc", "P0AA6"], "no_evidence", 1),
            ("continue", ["--dtc", "P0AA6"], "stopped", 1),
        ]:
            command("run_checkpoint_demo.py", action, "--thread-id", thread,
                    "--db", diagnosis_db, *extra)
            state = snapshot(build_diagnosis_graph, diagnosis_db, thread).values
            require(state["status"] == expected_status and state["tool_call_count"] == expected_count,
                    "跨进程诊断状态或预算不符合预期")
        require(state["stop_reason"] == "duplicate_tool_call", "重复调用未被拒绝")
        passed("checkpoint", "跨进程补问恢复：needs_info/0 → no_evidence/1 → 重复调用拒绝/1")

        result = build_diagnosis_graph(dtc_lookup=lookup_dtc_via_mcp).invoke(
            make_diagnosis_state(load_knowledge_chunks()))
        require(result["status"] == "no_evidence" and result["tool_call_count"] == 1
                and result["tool_trace"] == [{"tool_name": "lookup_dtc", "status": "success"}],
                "真实 stdio MCP 查询不符合预期")
        passed("mcp", "真实 stdio MCP 查询成功；固定资料缺少 P0AA6 证据，保持 no_evidence")

        def timeout(**arguments):
            raise TimeoutError("阶段演示：教学超时注入")

        result = build_diagnosis_graph(dtc_lookup=timeout).invoke(make_diagnosis_state([]))
        require(result["status"] == "needs_human" and result["stop_reason"] == "tool_timeout"
                and result["handoff_request"]["reason"] == "tool_timeout", "超时未进入复核")
        passed("tool_failure", "教学超时停止自动处理并返回本地复核请求")

        thread = "stage-order"
        order_args = ["--thread-id", thread, "--db", review_db, "--orders-db", orders_db]
        command("run_work_order_demo.py", "start", *order_args)
        command("run_work_order_demo.py", "edit", *order_args,
                "--title", "阶段演示：车辆故障人工复核")
        before = snapshot(build_work_order_graph, review_db, thread)
        require(before.interrupts and before.values["status"] == "pending_approval"
                and len(before.values["review_history"]) == 1 and not orders_db.exists(),
                "编辑后必须继续待审批，且不能提前写工单")
        print("\n待审批演示草稿：", flush=True)
        print(json.dumps(before.values["draft"], ensure_ascii=False, indent=2), flush=True)
        if args.scripted_review:
            print("审批来源：教学预设 approve，仅验证流程，不代表真人决策。", flush=True)
        else:
            decision = input("仅写入上述隔离演示目录。输入 approve 批准，其他输入取消：").strip()
            if decision != "approve":
                summary["status"] = "cancelled"
                print("已取消批准，未创建演示工单。", flush=True)
                return 2
        command("run_work_order_demo.py", "approve", *order_args)
        after = snapshot(build_work_order_graph, review_db, thread)
        require(not after.interrupts and after.values["status"] == "approved"
                and len(after.values["review_history"]) == 2 and not orders_db.exists(),
                "批准应结束审批，提交前仍不能写工单")
        passed("approval", "编辑后重新等待批准；批准结束审批，尚未提交工单")
        command("run_work_order_demo.py", "submit", *order_args)
        first = orders()
        command("run_work_order_demo.py", "submit", *order_args)
        second = orders()
        require(len(first) == 1 and first == second
                and first[0][1] == f"work-order:{thread}", "两次提交未保持同编号与单行记录")
        require(json.loads(first[0][2]) == after.values["draft"], "工单内容与批准记录不一致")
        summary["demo_work_order_id"] = first[0][0]
        passed("idempotency", f"同键两次提交仅一行，演示工单编号：{first[0][0]}")
        if args.base_url:
            command("check_agent_http.py", "--base-url", args.base_url)
            passed("http", "已启动服务的健康、MCP、补问和本地复核检查通过")
        else:
            summary["http"] = "not_requested"
        summary["status"] = "passed"
        print(f"\n阶段演示：{len(summary['checks'])} 项检查通过。GitHub 云端 CI 延后。", flush=True)
        return 0
    except (EOFError, KeyboardInterrupt):
        summary["status"] = "cancelled"
        print("演示被取消；报告保留已执行步骤。", flush=True)
        return 2
    except Exception as error:
        summary["status"] = "failed"
        summary["error"] = {"type": type(error).__name__, "message": str(error)}
        (output / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        print("演示失败：", str(error), file=sys.stderr, flush=True)
        return 1
    finally:
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("证据目录：", output, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
