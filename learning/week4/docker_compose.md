# 第四周：Docker Compose 部署只读 Agent

目标：一条命令启动容器，验证健康检查及 HTTP → 诊断图 → stdio MCP。此步不部署早期 Chroma/Qwen 服务，也不接入审批与工单写入。

## 1. 启动

在项目根目录执行：

```bash
cd /Users/jzr/Desktop/vehicle-diagnosis-agent
docker compose up --build -d --wait
docker compose ps
```

首次构建需联网下载 Python 和依赖。看到 agent 状态 healthy 后，访问 http://127.0.0.1:8002/health 与 http://127.0.0.1:8002/docs 。当前 8001 的 Conda 服务可以继续运行。

## 2. 诊断验收

在交互文档的 POST /diagnose 中执行：

```json
{"vehicle_id":"VIN-DEMO-001","symptom":"仪表提示绝缘故障","dtc_codes":["P0AA6"]}
```

预期 HTTP 200、status=no_evidence、tool_call_count=1、tool_data_source=mock，工具轨迹 success。固定真实资料没有匹配 P0AA6 证据，拒绝生成诊断建议属于预期行为。

将 dtc_codes 改为 []：预期 needs_info、调用 0 次。改为 ["P0123"]：预期 needs_human、stop_reason=tool_data_not_found、调用 1 次，返回本地复核请求。

同一请求重新执行仍独立计算预算，不构成跨轮会话恢复。

## 3. 查看日志和停止

```bash
docker compose logs --tail=100 agent
docker compose down
```

如果 8002 被占用，可用 AGENT_PORT=8003 docker compose up --build -d --wait，随后访问 8003。使用同一个项目目录执行 down，避免停止其他项目。

## 4. 配置与边界

- Dockerfile：Python 3.11、单次只读 HTTP 服务，非 root 运行；MCP 子进程由适配器按请求启动并关闭。
- compose.yaml：只绑定本机端口，根文件系统只读，/tmp 临时可写；不挂载主机数据目录、密钥或 Docker socket。
- .dockerignore：默认排除，仅放行运行代码、固定清单和清单内 12 篇资料。新增清单内文档时需同步放行。
- requirements-agent.txt 记录 7 项直接依赖；requirements-agent.lock.txt 固定已验收镜像中的 60 项直接及传递依赖。构建同时安装两者；早期 RAG 与完整测试继续使用原 requirements.txt/Conda 环境。
- /health 只验证进程存活，不能保证资料或 MCP 都可用；须额外执行诊断验收。
- 基础镜像摘要与完整运行依赖版本已固定；锁文件不含下载哈希，其他架构尚未实测。CI 与线上部署还未完成。

配置依据：[Docker Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)。

基础镜像使用 Docker 官方账号在 Amazon ECR 的 Python 3.11 slim 发布并固定摘要。本机首次访问 Docker Hub 超时，此地址已实测可拉取；没有修改主机网络配置。[官方发布目录](https://gallery.ecr.aws/docker/)

## 本次验证记录

2026-10-15 教练已实际构建并验证 linux/arm64 镜像：healthy、上述诊断分支、请求独立、非 root、只读文件系统、语料与依赖边界均通过；pip check 无冲突，全量测试 270 passed。临时验收使用 18002 并已关闭。默认配置仍为 8002，由学习者按第 1 节启动验收。其他 CPU 架构尚未实测。
