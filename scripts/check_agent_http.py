"""验证已启动的 Agent HTTP 服务；不会创建、停止容器或提交工单。"""

import argparse
import json
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    base = parser.parse_args().base_url.rstrip("/")

    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {path}")
            return json.load(response)

    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    require(request("/health") == {"status": "ok"}, "健康检查失败")
    require("/diagnose" in request("/openapi.json")["paths"], "缺少诊断接口")
    state = {"vehicle_id": "VIN-DEMO-001", "symptom": "仪表提示绝缘故障",
             "dtc_codes": ["P0AA6"]}
    for _ in range(2):
        result = request("/diagnose", state)
        require(result["status"] == "no_evidence" and result["tool_call_count"] == 1,
                "固定语料应无证据，且每次请求调用一次")
        require(result["citations"] == [] and result["tool_data_source"] == "mock",
                "无证据结果或模拟数据标记不正确")
        require(result["tool_trace"] == [{"tool_name": "lookup_dtc", "status": "success"}],
                "MCP 工具调用未成功")
    result = request("/diagnose", {**state, "dtc_codes": []})
    require(result["status"] == "needs_info" and result["tool_call_count"] == 0,
            "缺少 DTC 时应先补问")
    result = request("/diagnose", {**state, "dtc_codes": ["P0123"]})
    require(result["status"] == "needs_human" and result["stop_reason"] == "tool_data_not_found",
            "查无记录时应转本地人工复核")
    require(result["tool_call_count"] == 1 and result["handoff_request"] is not None,
            "人工复核请求或预算不正确")
    print("HTTP 冒烟检查通过：健康、接口、MCP 查询、请求独立、补问、人工复核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
