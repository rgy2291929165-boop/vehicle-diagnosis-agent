# 第四周：跨进程人工审批演示

- 负责人：学习者与教练；前置为审批图 10 项测试与全量 169 项测试通过。
- 目标：每次命令启动独立 Python 进程，通过相同数据库与 thread_id 找回暂停的审批。
- 产物：scripts/run_work_order_demo.py。默认数据库为 data/checkpoints/work_order_approval.sqlite，与诊断演示数据库分开。
- 输入为固定教学车辆的用户报告信息，不调用诊断工具。start/edit/approve/reject/show 处理审批，submit 才写入本地正式工单表。

依次运行：

```bash
python scripts/run_work_order_demo.py start --thread-id week4-approval-001
python scripts/run_work_order_demo.py edit --thread-id week4-approval-001 --description "请先联系用户确认故障出现时间。"
python scripts/run_work_order_demo.py approve --thread-id week4-approval-001
python scripts/run_work_order_demo.py show --thread-id week4-approval-001
```

- start：pending_approval，等待人工决策为是，已提交决策数为 0。
- edit：pending_approval，描述更新，继续等待，决策数为 1。
- approve：approved，不再等待，保留修改后的描述，决策数为 2。
- show：不执行图，显示当前状态与含草稿副本的完整审批历史。
- 重复 start 或对终态继续审批会报错，不覆盖原记录。重复演示应更换 thread_id。
- 拒绝分支：用新 thread_id 执行 start，再运行 reject --thread-id 对应ID --reason "需要重新确认信息"。
- 无效文本会在图中记录 invalid，保留原草稿并继续暂停，CLI 返回退出码 2；可随后提交正确决策。
- 禁止 approve 夹带 --description 等编辑参数；修改和批准必须分两次明确决策。
- 验收：独立进程启动、编辑、批准、拒绝、查看、输入更正、会话隔离及终态保护。
- 正式提交（2026-10-15 新增）：批准后运行 `python scripts/run_work_order_demo.py submit --thread-id week4-approval-001`；重跑相同命令返回相同工单编号。默认工单库为 data/work_orders/work_orders.sqlite，可用 --orders-db 指定。
- 同一 thread_id 对应一个工单请求，在共用同一工单库的场景中应保持唯一。相同幂等键但已批准内容不同会报冲突，不覆盖已有记录。提交读取 checkpoint 中的已批准内容，不接受命令行夹带修改。
- show 仅读取审批 checkpoint；正式工单编号由 submit 输出。批准与提交为两个独立动作。
- 本步接口与测试见 learning/week4/work_order_store.md；故障转人工、MCP 和部署继续在后续推进。
