"""分次运行命令，演示工单草稿的人工审批与跨进程恢复。"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.work_order_graph import build_work_order_graph
from app.work_order_store import create_work_order_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "edit", "approve", "reject", "show", "submit"])
    parser.add_argument("--thread-id", required=True)
    parser.add_argument(
        "--db", type=Path,
        default=PROJECT_ROOT / "data" / "checkpoints" / "work_order_approval.sqlite",
    )
    parser.add_argument(
        "--orders-db", type=Path,
        default=PROJECT_ROOT / "data" / "work_orders" / "work_orders.sqlite",
        help="submit 写入的本地工单数据库",
    )
    parser.add_argument("--title", help="edit 时的新标题")
    parser.add_argument("--description", help="edit 时的新描述")
    parser.add_argument("--reason", help="reject 时的拒绝原因")
    args = parser.parse_args()

    if not args.thread_id.strip():
        parser.error("--thread-id 不能为空")
    if args.action != "edit" and (args.title is not None or args.description is not None):
        parser.error("--title 和 --description 仅用于 edit")
    if args.action != "reject" and args.reason is not None:
        parser.error("--reason 仅用于 reject")

    decision = {"action": args.action}
    if args.action == "edit":
        changes = {
            name: value for name, value in (
                ("title", args.title), ("description", args.description),
            ) if value is not None
        }
        if not changes:
            parser.error("edit 至少需要 --title 或 --description")
        decision["changes"] = changes
    elif args.action == "reject":
        if args.reason is None:
            parser.error("reject 需要 --reason")
        decision["reason"] = args.reason

    database = args.db.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": args.thread_id.strip()}}
    work_order = None

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_work_order_graph(saver)
        snapshot = graph.get_state(config)
        if args.action == "start":
            if snapshot.values:
                parser.error("此会话已存在，请使用 show 或继续审批，或换一个 --thread-id")
            graph.invoke({
                "vehicle_id": "VIN-DEMO-001",
                "symptom": "仪表提示绝缘故障",
                "dtc_codes": ["P0AA6"],
            }, config)
        elif args.action == "show":
            if not snapshot.values:
                parser.error("未找到此会话，请检查 --db 和 --thread-id")
        elif args.action == "submit":
            if not snapshot.values:
                parser.error("未找到此会话，请先生成并批准草稿")
            if snapshot.next or snapshot.interrupts:
                parser.error("审批尚未结束，不能提交工单")
            try:
                work_order = create_work_order_once(
                    snapshot.values,
                    idempotency_key=f'work-order:{config["configurable"]["thread_id"]}',
                    database_path=args.orders_db,
                )
            except ValueError as error:
                parser.error(str(error))
        else:
            if not snapshot.values:
                parser.error("未找到此会话，请先用相同 --db 和 --thread-id 执行 start")
            if (
                snapshot.values.get("status") != "pending_approval"
                or snapshot.next != ("review_work_order",)
                or not snapshot.interrupts
            ):
                parser.error("当前会话没有正在等待决策的草稿；已批准或拒绝的会话不能重复审批")
            graph.invoke(Command(resume=decision), config)

        snapshot = graph.get_state(config)
        state = snapshot.values
        draft = state["draft"]
        print("进程 PID：", os.getpid())
        print("数据库：", database)
        print("会话 ID：", config["configurable"]["thread_id"])
        print("演示范围：人工审批与本地工单提交")
        print("状态：", state["status"])
        print("等待人工决策：", "是" if snapshot.interrupts else "否")
        print("车辆：", draft["vehicle_id"])
        print("故障码：", "、".join(draft["dtc_codes"]))
        print("标题：", draft["title"])
        print("描述：", draft["description"])
        print("已提交决策数：", len(state["review_history"]))
        print("校验错误：", state["review_error"])
        if "rejection_reason" in draft:
            print("拒绝原因：", draft["rejection_reason"])
        print("节点轨迹：", " → ".join(state["trace"]))
        if args.action == "show":
            print("审批历史：", json.dumps(state["review_history"], ensure_ascii=False, indent=2))
        if work_order is not None:
            print("工单数据库：", args.orders_db.expanduser().resolve())
            print("正式工单编号：", work_order["work_order_id"])
            print("正式工单状态：", work_order["status"])
            print("幂等键：", work_order["idempotency_key"])

        return 2 if state["review_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
