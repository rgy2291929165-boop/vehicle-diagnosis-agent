# 第四周：stdio 只读 DTC MCP 服务

- 负责人：学习者与教练；前置为进程内诊断工具、故障处理与工单审批已实现，全量基线 213 passed。
- 目标：在独立服务进程中暴露一个 lookup_dtc，通过客户端发现工具、读取参数协议并查询模拟目录。
- 依赖：官方 mcp==2.3.0，使用 v2 的 MCPServer、Client、StdioServerParameters；不照搬 v1 的 FastMCP/ClientSession 示例。
- 选择：先用 SDK 与 stdio，协议与生命周期交给 SDK；手写 JSON-RPC 增加学习负担，HTTP/容器部署留到后续。
- 服务端：app/dtc_mcp_server.py，仅注册只读 lookup_dtc。参数 vehicle_id、dtc_code 为非空字符串；去首尾空白，故障码由现有函数转大写。
- 输入与输出复用现有模拟目录；结构化结果增加 data_source=mock。查无记录返回 is_error=True，并在元数据中标注 failure_reason=tool_data_not_found；SDK 的结果通过 is_error 与 structured_content 区分成功与失败。
- 客户端：app/dtc_mcp_client.py，以当前 sys.executable 启动 python -m app.dtc_mcp_server，并固定项目 cwd；async with 退出时由 SDK 关闭服务子进程，读超时设为 10 秒。
- 只读标记为行为提示；实际只读边界是服务仅注册模拟查询函数，没有注册工单写入、修改和删除工具。
- 演示：python scripts/run_dtc_mcp_demo.py。客户端自动启动服务，无需另开终端。单独启动服务会等待 stdin 中的 MCP 消息，这是 stdio 服务的正常行为。
- 服务端 stdout 专用于协议，不添加普通 print；演示结果由客户端显示。
- 测试：工具列表及参数协议、结构化输出与模拟标记、输入校验、查无记录、拒绝未注册写工具、真实 stdio 子进程、任意工作目录启动与错误后继续查询。
- 验收命令：python -m pytest tests/test_dtc_mcp.py -q；python -m pytest -q；python scripts/run_dtc_mcp_demo.py。
- 边界：本任务先验证独立服务与客户端；诊断图的可选接入现见 learning/week4/mcp_diagnosis_adapter.md。此工作流不评价实车诊断准确率。
- 官方来源：https://github.com/modelcontextprotocol/python-sdk；https://py.sdk.modelcontextprotocol.io/servers/tools/；https://py.sdk.modelcontextprotocol.io/client/；https://py.sdk.modelcontextprotocol.io/client/transports/；https://pypi.org/pypi/mcp/2.3.0/json。
- 后续：验证 learning/week4/mcp_diagnosis_adapter.md 中的诊断图接入，再推进部署、健康检查和 CI。

## 本步验证结果（2026-10-15）

- 依赖安装完成，pip check 无损坏依赖。
- 定向 13 passed；全量 226 passed（API 文档导入测试隔离到临时目录）。
- 默认演示发现唯一 lookup_dtc，read_only_hint=True，is_error=False，结构化结果 data_source=mock。
- --dtc P0123 返回明确查无记录错误，退出码 1，未显示成功查询结果。
