"""诊断图通过 stdio MCP 查询 DTC，继续使用现有检索和防护流程。"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.diagnosis_graph import build_diagnosis_graph
from app.dtc_mcp_adapter import lookup_dtc_via_mcp
from app.knowledge_corpus import load_knowledge_chunks
from scripts.run_diagnosis_demo import make_state, show_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtc", default="P0AA6")
    args = parser.parse_args()
    graph = build_diagnosis_graph(dtc_lookup=lookup_dtc_via_mcp)
    result = graph.invoke(make_state(load_knowledge_chunks(), dtc_codes=[args.dtc]))
    print("DTC 调用方式：独立 stdio MCP 服务")
    print("数据范围：模拟 DTC 目录 + 第二周固定资料")
    show_case(args.dtc, result)
    if result["handoff_request"]:
        print("人工复核请求：", json.dumps(result["handoff_request"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
