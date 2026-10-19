"""分次运行此脚本，演示同一 thread_id 的 SQLite 会话恢复。"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.checkpoint.sqlite import SqliteSaver

from app.diagnosis_graph import build_diagnosis_graph
from app.knowledge_corpus import load_knowledge_chunks
from scripts.run_diagnosis_demo import make_state, show_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "continue", "show"])
    parser.add_argument("--thread-id", required=True, help="同一会话始终使用相同 ID")
    parser.add_argument(
        "--db", type=Path,
        default=PROJECT_ROOT / "data" / "checkpoints" / "diagnosis.sqlite",
    )
    parser.add_argument("--dtc", help="continue 时补充的故障码，例如 P0AA6")
    args = parser.parse_args()

    if not args.thread_id.strip():
        parser.error("--thread-id 不能为空")
    if args.action == "continue" and (not args.dtc or not args.dtc.strip()):
        parser.error("continue 需要 --dtc，例如 --dtc P0AA6")
    if args.action != "continue" and args.dtc is not None:
        parser.error("--dtc 仅用于 continue")

    database = args.db.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": args.thread_id}}

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_diagnosis_graph(checkpointer=saver)
        saved = graph.get_state(config).values

        if args.action == "start":
            if saved:
                parser.error("此会话已存在，请使用 continue/show，或换一个 --thread-id")
            chunks = load_knowledge_chunks()
            result = graph.invoke(make_state(chunks, dtc_codes=[]), config)
        elif args.action == "continue":
            if not saved:
                parser.error("未找到此会话，请先用相同 --db 和 --thread-id 执行 start")
            # 只提交新增信息，其余字段从 SQLite 中恢复。
            result = graph.invoke({"dtc_codes": [args.dtc.strip().upper()]}, config)
        else:
            if not saved:
                parser.error("未找到此会话，请检查 --db 和 --thread-id")
            result = saved

        print("进程 PID：", os.getpid())
        print("数据库：", database)
        print("会话 ID：", args.thread_id)
        print("资料：第二周固定的真实资料；工具：只读模拟工具")
        show_case(args.action, result)


if __name__ == "__main__":
    main()
