# 第四周：Agent CI 自动检查

## 本步做什么

GitHub Actions 工作流在 push、pull_request 或手动触发时运行：安装固定运行/测试依赖 → Agent 测试 → 20 条工作流验收 → 镜像构建 → 容器健康及 HTTP/MCP 检查 → 清理容器并保留测试报告。

工作流只读仓库，不自动发布镜像、部署线上服务或提交工单，也不需要模型 API Key。

## 先在本地运行同一组检查

```bash
cd /Users/jzr/Desktop/vehicle-diagnosis-agent
conda activate vehicle-agent
python scripts/run_agent_ci.py
```

报告写入 evaluation/week4/ci-runs/local/：pytest.xml、ci_summary.json 和 acceptance/ 下的 20 条轨迹/汇总。该目录已忽略，不会覆盖第三周正式报告或第二周冻结结果。任一阶段失败，脚本最终返回非零退出码。

检查已经启动的本机容器：

```bash
python scripts/check_agent_http.py --base-url http://127.0.0.1:8002
```

该脚本仅发送健康和只读诊断请求，不创建或停止容器。P0AA6 预期 no_evidence；缺 DTC 先补问；P0123 返回本地复核请求。

## 测试范围

CI 使用 requirements-ci.txt，包含已锁定的 Agent 运行依赖及固定 pytest 工具。测试包括状态图、检索、工具 Guard、SQLite checkpoint、审批/幂等工单、故障处理、真实 stdio MCP 和 FastAPI 依赖覆盖。

CI 明确排除 tests/test_api.py 和 tests/test_llm.py：两者属于早期向量 RAG/Qwen 路径，需要原环境中的其他依赖。原有完整回归仍保留：

```bash
python -m pytest -q
```

不能将 CI 的测试数量冒称完整项目全部测试。测试中的工单写入使用临时数据库，不接触演示数据库。

## GitHub 上如何运行

配置文件为 .github/workflows/agent-ci.yml；仓库 checkout、Python setup 和报告上传 action 都固定提交摘要。云端使用 Ubuntu 24.04、Python 3.11，任务超时 20 分钟，报告保留 7 天；Compose 使用独立项目名和端口 18002，始终尝试清理。

当前桌面项目尚未建立 Git 仓库，也没有已确认的远端。因此本步仅准备配置并验证本地流程，不能声称 GitHub 上已出现绿色检查。创建/选择远端和首次推送属于下一步，须先确认目标仓库与提交范围；不要将 .env、资料外的私有文件或本地数据库公开上传。

之后在 GitHub 仓库的 Actions 页面找到 Agent CI，查看本次运行日志和上传报告。只有真实云端运行成功后才记录云端 CI 验收通过。

官方依据：[工作流语法](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)、[checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)、[upload-artifact](https://github.com/actions/upload-artifact)。

## 本次教练验证

2026-10-15：干净 Linux arm64 容器中关闭网络、挂载只读源码，258 项 Agent 测试与 20/20 工作流均通过；本机同一脚本也通过。actionlint v1.7.12 语法检查、隔离 Compose 构建与真实 HTTP/MCP 检查通过。临时容器已清理，未操作用户 8002 服务。

258 与上一项完整回归的 270 不同，是因为这里明确排除早期 RAG API/LLM 两个文件。CI 源码未删除任何原有测试。云端 GitHub Actions 尚未执行。
