"""诊断图演示：真实资料与教学片段分开显示。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.diagnosis_graph import build_diagnosis_graph
from app.diagnosis_input import make_diagnosis_state
from app.knowledge_corpus import load_knowledge_chunks


def make_state(chunks, **overrides):
    return make_diagnosis_state(chunks, **overrides)


def show_case(title, result):
    print(f"\n【{title}】")
    print("状态：", result["status"])
    print("终止原因：", result["stop_reason"])
    print("调用次数：", result["tool_call_count"])
    print("回答：", result["answer"])
    print("引用：", result["citations"])
    print("节点轨迹：", " → ".join(result["trace"]))
    print("工具轨迹：", result["tool_trace"])


def main():
    chunks = load_knowledge_chunks()
    graph = build_diagnosis_graph()

    print("真实文档数：", len({item["document_id"] for item in chunks}))
    print("真实片段数：", len(chunks))

    first = graph.invoke(make_state(chunks))
    show_case("真实资料：P0AA6 无匹配候选", first)

    teaching_chunks = [{
        "chunk_id": "demo-only:0",
        "document_id": "demo-only",
        "text": "P0AA6 教学片段，仅用于验证检索和引用流程。",
        "source": "demo/fixture",
    }]
    show_case(
        "教学片段命中：仅验证流程",
        graph.invoke(make_state(teaching_chunks)),
    )

    show_case(
        "缺少故障码",
        graph.invoke(make_state(chunks, dtc_codes=[])),
    )

    show_case(
        "预算耗尽",
        graph.invoke(make_state(chunks, tool_call_count=2)),
    )

    show_case(
        "重复调用",
        graph.invoke(make_state(
            chunks,
            tool_call_count=first["tool_call_count"],
            seen_tool_calls=first["seen_tool_calls"],
            tool_trace=first["tool_trace"],
        )),
    )


if __name__ == "__main__":
    main()