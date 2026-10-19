"""只在本进程内注入模拟工具故障，验证人工复核请求。"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import tool_router
from app.diagnosis_graph import build_diagnosis_graph
from scripts.run_diagnosis_demo import make_state, show_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=sorted(tool_router.ALLOWED_TOOLS), default="lookup_dtc")
    parser.add_argument("--fault", choices=["timeout", "unavailable", "not_found"], default="timeout")
    args = parser.parse_args()
    error_type = {
        "timeout": TimeoutError, "unavailable": ConnectionError, "not_found": LookupError,
    }[args.fault]

    def fail(**arguments):
        raise error_type(f"教学故障注入：{args.fault}")

    with patch.dict(tool_router.TOOL_REGISTRY, {args.tool: fail}):
        result = build_diagnosis_graph().invoke(make_state([], requested_tool=args.tool))
    show_case(f"{args.tool} / {args.fault}", result)
    print("人工复核请求：", json.dumps(result["handoff_request"], ensure_ascii=False, indent=2))
    print("此演示只生成本地复核请求，尚未发送给真实客服或维修人员。")


if __name__ == "__main__":
    main()
