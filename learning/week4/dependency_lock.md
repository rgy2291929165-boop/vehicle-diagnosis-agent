# 第四周：固定 Agent 容器依赖版本

## 本步目标

在已经验收的 Linux Agent 镜像基础上，记录全部运行依赖版本，重建后验证版本没有漂移。仅处理只读 Agent 镜像，不改变 Conda 环境或早期 RAG 的依赖。

## 两个依赖文件

- requirements-agent.txt：7 项直接依赖，表达应用主动使用的库。
- requirements-agent.lock.txt：由已验收的 Python 3.11 / linux/arm64 镜像导出，包含 60 项直接与传递运行依赖。

Dockerfile 同时安装两个文件；直接依赖与锁文件冲突时构建会失败，避免只修改一个文件而静默忽略另一个。

固定基础镜像摘要和全部运行包版本，可以减少版本变化；本文件没有包下载哈希，不承诺镜像逐字节相同。只实测 linux/arm64，其他平台需单独构建验证。pip/setuptools 等构建工具由固定基础镜像提供，不属于此运行依赖表。

## 学习者验收

在项目根目录执行：

```bash
docker compose up --build -d --wait
docker compose exec -T agent python -m pip check
```

预期显示 No broken requirements found.，并且 8002 的 /health 和此前 P0AA6 诊断仍符合预期。up 会使用新镜像更新本项目容器；不需要删除本机数据库或资料。

可查看实际版本：

```bash
docker compose exec -T agent python -m pip freeze
```

## 后续维护

升级时先调整直接依赖，在隔离的 Linux 容器中重新解析、安装并导出版本，再审阅差异、运行 pip check 和容器 HTTP/MCP 验收。不使用本机 macOS 全环境的 pip freeze 覆盖此文件；不要为了构建通过随意取消版本限制。

下一项为 CI 自动检查。当前没有连接 Git 远端或执行云端 CI，也尚未宣称第四周整体完成。

## 本次教练验收

2026-10-15 已按锁重建 linux/arm64 镜像。临时 18003 容器健康与 HTTP/MCP 分支正常，pip check 通过，60 项实际版本与锁定前镜像完全一致。临时验收容器已关闭；学习者当前 8002 容器保持原状，按上面的 up 命令更新即可。
