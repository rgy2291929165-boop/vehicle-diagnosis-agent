# 第四周：诊断图接入 MCP DTC 适配器

- 负责人：学习者与教练；前置为独立 MCP 服务/客户端验收通过，全量基线 226 passed。
- 目标：诊断图以可选依赖注入接入 MCP 查询，同时保留允许列表、参数检查、预算、去重和本地人工复核路径。
- 接口：build_diagnosis_graph(checkpointer=None, *, dtc_lookup=None)；传入 lookup_dtc_via_mcp 时，仅 DTC 走 MCP，其余工具沿用原实现。默认仍支持原无参调用。
- 选择：为每张图传入工具适配器，不运行期修改全局 TOOL_REGISTRY；无需在本步重写整张图为异步或引入新的工具平台。
- 调用顺序：图规划 → Guard 预算/签名 → Router 允许列表/参数检查 → MCP 适配器 → stdio 服务。拒绝的调用不能启动 MCP 子进程。
- 共享 DtcQuery/DtcResult 契约校验请求与返回；成功结果必须标记 mock，并且车辆、DTC 与请求一致。结构错误转 invalid_tool_result，不能伪装成查询成功。
- 服务查无记录在 is_error=True 结果的元数据中声明 failure_reason=tool_data_not_found；适配器按原因归类，不解析中文文本。
- 适配器将 SDK 的读超时、连接关闭/进程启动失败归类为现有超时/不可用错误；其他远端协议/工具错误转 tool_remote_error。只处理已知异常子组，混合的未知程序异常继续报告。
- 同步 lookup_dtc_via_mcp 用 asyncio.run 运行异步客户端；异步调用方使用图的 ainvoke，或直接 await lookup_dtc_via_mcp_async，避免在运行中的事件循环里调用同步桥接。
- 每次获准 DTC 调用启动一个本地子进程并在查询结束关闭。本步未增加长连接池或自动重试。
- 演示命令：python scripts/run_mcp_diagnosis_demo.py；默认真实资料仍无 P0AA6 候选，因此预期 no_evidence、工具调用成功且调用次数为 1。
- 查无记录演示：python scripts/run_mcp_diagnosis_demo.py --dtc P0123；预期 needs_human/tool_data_not_found。
- 本步不增加 LLM、不改冻结资料，不会因使用 MCP 就把无证据查询变成真实诊断结论。
- 下一项：学习者验收后，推进可部署入口、健康检查、依赖隔离与 CI；第四周尚未完成。

## 本步验证结果（2026-10-15）

- 定向 23 passed；全量 249 passed；原有 20 条基础工作流 20/20（临时输出目录）。
- 默认演示 no_evidence、调用 1 次、工具 success；P0123 为 needs_human/tool_data_not_found。
- 真实立即退出服务与不响应服务分别进入 tool_unavailable 和 tool_timeout；混合未知程序异常继续报告。
- 无 checkpoint 的 ainvoke 已测试；使用异步持久化时需另选异步 saver，本步不宣称同步 SqliteSaver 支持异步图执行。
