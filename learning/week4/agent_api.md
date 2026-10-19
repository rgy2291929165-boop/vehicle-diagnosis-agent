# 第四周：Agent HTTP 服务入口与存活检查

- 负责人：学习者与教练；前置为 MCP 诊断图验收，全量基线 249 passed。
- 目标：将单次只读诊断作为 HTTP 接口提供，具备轻量存活检查、可解释错误与可覆盖依赖。
- 产物：app/agent_api.py、app/diagnosis_input.py、tests/test_agent_api.py；教学脚本共享状态初始化，旧 RAG API 的文档导入测试隔离到临时目录。
- 选择：建立专门的 Agent API 入口，避免将旧 Qwen/向量 RAG 与当前无 LLM 诊断接口混在一起；此步不拆微服务或增加鉴权平台。

启动：

```bash
python -m uvicorn app.agent_api:app --host 127.0.0.1 --port 8001
```

- 进程持续运行表示正在监听请求；保持此终端开启。Control+C 停止自己启动的服务。
- 存活检查：http://127.0.0.1:8001/health，预期 {"status":"ok"}。
- 交互文档：http://127.0.0.1:8001/docs，可用 POST /diagnose 的 Try it out 发起请求。

请求示例：

```json
{
  "vehicle_id": "VIN-DEMO-001",
  "symptom": "仪表提示绝缘故障",
  "dtc_codes": ["P0AA6"]
}
```

- 默认 DTC 经独立 stdio MCP 查询；资料来自第二周固定语料，预期工具 success、调用 1 次、最终 no_evidence。
- /diagnose 当前为单次只读查询，每次请求重新建立预算和轨迹，不接收 thread_id 或客户端状态；跨轮 checkpoint/人工审批/正式工单仍由已有 CLI 演示，不在此入口暴露写操作。
- 一次最多传一个 DTC，与当前规划器单码查询能力一致；可选 requested_tool 为三个已允许的只读工具，库存还需 part_number。
- 缺少业务字段返回 needs_info，预期工具故障返回 needs_human；非法输入 HTTP 422，资料文件缺失/哈希不符等返回 HTTP 503，意外程序错误保留 HTTP 500。
- 响应包含回答、来源、状态、调用次数与轨迹、复核材料，标记 tool_data_source=mock；不直接返回完整语料和内部去重签名。
- /health 只表示 HTTP 进程存活，不校验资料完整性或 MCP 可用性；不会加载向量库/Embedding/Qwen，也不会发起 MCP 查询。此步没有宣称实现全面 readiness 检查。
- get_diagnosis_graph 与 get_knowledge_chunks 使用 FastAPI Depends，可以在离线测试中覆盖；另保留一条实际 MCP 集成测试。
- 验收命令：python -m pytest tests/test_agent_api.py -q；python -m pytest -q。
- 后续：Docker Compose、依赖可复现安装、健康检查配置与 CI；本步只验证本地 HTTP 入口，不代表已完成容器部署或线上发布。

## 本步验证结果（2026-10-15）

- 定向 20 passed；普通全量 269 passed；原有基础工作流 20/20，报告写入临时目录。
- 真实临时 Uvicorn 服务验证健康检查、文档和三种诊断结果后已关闭；尚未进行 Docker 或线上发布。
- 旧文档导入测试现自带临时目录隔离，全量测试无需外部运行器修改应用状态。
