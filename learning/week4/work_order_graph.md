# 第四周：工单审批暂停与恢复

- 负责人：学习者与教练；前置为草稿与人工决策纯函数通过验收，全量基线 159 passed。
- 目标：独立审批图通过 interrupt 暂停，使用相同 thread_id 和 Command(resume=decision) 接收人工决策。
- 接口：app.work_order_graph.build_work_order_graph(checkpointer)，必须提供 checkpointer；本步使用 SQLite saver。
- 初始输入：vehicle_id、symptom、dtc_codes；prepare_work_order_draft 生成草稿并初始化历史与轨迹。
- 图流程：START → prepare_work_order_draft → review_work_order。审批节点调用 interrupt 展示草稿、可选动作和上次错误。
- approve/reject 后走 END；edit 后继续 pending_approval，并在下一次审批节点执行时暂停，等待新内容的明确批准。
- 已知的决策 ValueError 会保留草稿、记录无效尝试和错误，并再次暂停，以便更正；意外程序异常继续向外报告。
- review_history 保留每次已提交决策、结果状态、校验错误和对应草稿副本；trace 只记录已完成的节点更新，不在暂停前反复追加日志。
- 恢复会从审批节点开头执行，因此 interrupt 之前只展示信息，不生成正式工单或执行外部副作用。
- 架构选择：独立图复用现有纯函数，使诊断查询与审批状态互不干扰；直接合并诊断图或提前增加工单库会扩大本次验收范围。
- 本步验证：初始暂停、批准/拒绝结束、修改后再次暂停、SQLite 重开后恢复、无效决策更正、会话隔离、意外异常传播。
- 命令：python -m pytest tests/test_work_order_graph.py -q；然后 python -m pytest -q。
- 产物：app/work_order_graph.py、tests/test_work_order_graph.py 和本任务说明。
- 边界：approved 是已审核草稿状态；正式工单数据库写入、幂等与跨进程审批 CLI 演示仍在后续步骤。
