# 第四周：五分钟本地阶段演示

## 本轮目标

把分散的已有模块演示串成一个可重复入口，并留下日志与验收汇总。用户已决定 GitHub 上传后置；云端 Actions 记为延期未验收，不阻塞本地演示，也不据此宣称第四周全部验收完成。

## 运行

在 Conda 的 vehicle-agent 环境中执行：

```bash
cd /Users/jzr/Desktop/vehicle-diagnosis-agent
python scripts/run_week4_demo.py
```

先看到 checkpoint、MCP、超时复核三项 PASS，再展示演示草稿。阅读草稿后输入 approve 并回车，继续批准与两次幂等提交。输入其他内容将取消，退出码 2，演示工单不会创建；已有演示 checkpoint 和日志仍会保留。

如果本机 8002 容器仍在运行，可以把 HTTP 检查也纳入本次演示：

```bash
python scripts/run_week4_demo.py --base-url http://127.0.0.1:8002
```

这将执行 6 项检查。脚本不会启动或停止 HTTP 服务；未传 --base-url 时只执行 5 项本地模块检查，报告明确记录 HTTP 未请求。

每次运行在 evaluation/week4/demo-runs/ 下创建带时间和随机后缀的新目录：diagnosis.sqlite、review.sqlite、orders.sqlite、分步命令日志、summary.json。它们都是本次教学数据，不使用 data/checkpoints 或 data/work_orders 中的既有演示库。目录已加入 .gitignore。

## 五分钟讲解顺序

| 时间 | 展示 | 能证明什么 |
|---|---|---|
| 0:00–0:40 | 项目问题与边界 | 用户信息先检查，缺信息先补问；工具是模拟目录，当前无实车正确率结论 |
| 0:40–1:30 | 三个独立 checkpoint 命令 | 缺码 needs_info/0，跨进程补齐后 no_evidence/1，同调用被拒且次数仍为 1 |
| 1:30–2:15 | stdio MCP 查询与超时复核 | 独立 MCP 进程查询；真实资料没有 P0AA6 证据就不生成建议；超时返回本地复核请求 |
| 2:15–3:40 | 草稿编辑、暂停与输入 approve | 编辑后重新待审批；批准只结束审批；submit 才向独立演示库写工单 |
| 3:40–4:20 | 同一键两次提交 | 编号一致，数据库只有一行，内容与批准快照一致 |
| 4:20–5:00 | 可选 HTTP 检查、汇总与已有测试报告 | 容器 HTTP→图→MCP；本地 CI 258 项及工作流 20/20，完整回归上一项为 270；云端尚未运行 |

可以这样介绍：

> 我用 LangGraph 把资料完整性检查、工具调用和候选检索组织成有状态工作流。工具调用有参数校验、调用预算和重复拒绝；资料不支持当前故障码时返回 no_evidence。SQLite checkpoint 保留跨进程状态；工单编辑后必须重新批准，写入使用幂等键。DTC 查询通过独立 stdio MCP 子进程，单次只读诊断提供 FastAPI 和 Docker Compose 入口。

随后补充当前边界：当前工具使用固定模拟目录，Agent 路由由确定性规则驱动；没有连接车辆、真实人工队列或企业工单系统。诊断图与审批图仍是独立模块，HTTP 只接单次只读诊断。无证据拒答验证的是流程边界，不能当成实车诊断准确率。

## 自动复演与证据

教练/自动验证可以显式使用：

```bash
python scripts/run_week4_demo.py --scripted-review
```

该模式的批准来自教学预设，控制台与报告都会标注 scripted_fixture，不能描述成真人审批。日常展示请使用默认交互模式。

成功退出码为 0，summary.json 的 status 为 passed；取消为 2/cancelled，异常为 1/failed，异常日志保留在本次目录。报告不替代真实用户验收或云端 CI 记录。

## 当前验收状态

| 项目 | 状态与证据 |
|---|---|
| 既有 checkpoint、人工决策与工单幂等 | 先前测试及学习者演示已验证，阶段脚本再次复演 |
| MCP、HTTP 与 Docker | 本地实测通过，学习者已确认容器可用 |
| 本地 CI 等价流程 | 教练验证 258 passed、20/20；学习者上一项尚未提交运行结果 |
| 新的阶段演示 | 教练教学预设模式 6 项通过、交互取消通过；学习者默认交互模式输入 approve，5 项验收通过 |
| GitHub 上传和云端 Actions | 用户明确延期，尚未执行 |
| 实车诊断、真实人工队列、企业工单、线上部署 | 未验收，不计为已交付 |

学习者已完成交互演示，PASS、工单编号和 summary.json 均已核对。接下来根据总学习计划进入后续内容；GitHub 延期事项保留。

## 本次教练复演记录

2026-10-15：使用 --scripted-review 与独立 18006 HTTP 容器，6 项检查全部通过，教学工单两次提交仅一行。另在默认模式输入 cancel，退出码 2、summary cancelled，未创建工单库。原有诊断/审批/工单数据库 SHA-256 前后相同。临时容器已关闭，用户服务未操作。此记录是教学自动验证，不是学习者真人批准记录。

## 学习者交互验收

2026-10-15，运行 20261015T065215Z-fff4316f：学习者阅读草稿后输入 approve，5/5 通过。summary.json 为 passed/interactive；本次 orders.sqlite 经只读查询确认仅一条，编号 a6a6b4ab-af0d-45ae-bf98-32da055179ab、状态 open。本次未传 --base-url，HTTP 记为 not_requested，不计入本次五项检查。
