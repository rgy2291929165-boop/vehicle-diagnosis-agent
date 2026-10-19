# 第四周：工具故障与人工复核请求

- 负责人：学习者与教练；前置为诊断图、checkpoint、审批与幂等工单存储已实现，全量基线 189 passed。
- 目标：工具报告预期运行故障时终止自动诊断，返回可解释状态、错误轨迹和本地人工复核请求。
- 预期故障：TimeoutError → tool_timeout；ConnectionError → tool_unavailable；模拟目录精确的 LookupError → tool_data_not_found。
- 边界：KeyError、IndexError、ValueError、普通 RuntimeError 等程序或参数错误继续报错，不包装成预期业务故障。新外部工具适配器应按约定报告预期故障。
- Router 记录 error 轨迹并抛出 ToolExecutionFailed，保留原始异常 cause；Guard 沿用失败消耗预算、保留签名的规则。
- 图返回 needs_human，next_action 为 handoff_to_human，stop_reason 为故障原因；执行 handoff_to_human 节点后结束，不检索资料、不格式化诊断答案、不自动重试。
- handoff_request 包含车辆标识、用户报告、失败调用、错误记录与调用次数，数据使用独立副本；每轮完整性检查先清除旧请求、旧检索和旧引用。
- 选择：把故障归类放在 Router 的真实调用边界，图只处理类型明确的 ToolExecutionFailed；不在图中泛捕获 Exception 或把所有编程错误转成人工请求。
- 本步处理工具抛出的超时报告，不实现同步函数的强制超时终止。当前工具均为模拟实现，真实网络适配器的请求超时需在接入时设置。
- 演示命令：python scripts/run_tool_failure_demo.py --tool lookup_dtc --fault timeout；也可选择 unavailable/not_found 和另外两个工具。
- 故障注入只在演示脚本的 patch 上下文中发生，不增加生产图的绕过开关，不写入工单库，不发送真实消息。
- 验收：三种故障与三个工具、错误原因与轨迹、失败预算、SQLite 重开后保留信息、重复调用拦截、旧请求清理、数据独立，以及原有正常流程回归。
- 测试命令：python -m pytest tests/test_tool_failures.py -q；然后 python -m pytest -q。
- 当前产物是可供后续人工处理的本地请求；真实人工工单队列、指派与通知尚未接入。本步不代表已联系维修人员。

## 本步验证结果（2026-10-15）

- 定向 24 passed，全量 213 passed；原有基础工作流 20/20 通过，报告写入临时目录。
- 超时演示输出 needs_human、tool_timeout、调用次数 1，引用为空，节点轨迹结束于 handoff_to_human。
- 后续重复调用预算与签名不丢失；意外程序错误的传播行为通过测试保留。
