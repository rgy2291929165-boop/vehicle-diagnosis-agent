# 第四周：人工决策校验

- 负责人：学习者与教练；前置为草稿生成验收通过，全量基线 127 passed。
- 目标：实现纯函数 apply_work_order_decision(draft, decision)，先验证状态转换与输入约束，再接入图。
- 输入草稿由 build_work_order_draft 生成，且 status 必须为 pending_approval。
- approve：决策为 {"action": "approve"}；原内容保留，状态改为 approved。
- edit：决策含 action 和非空 changes；只允许编辑 title、description，内容必须是非空字符串。编辑后仍为 pending_approval，必须另行批准。
- reject：决策含 action 和非空文本 reason；返回 rejected 与 rejection_reason。
- 不接受未知决策字段；不允许借编辑修改车辆标识、用户报告的故障现象、故障码或审批状态。
- 返回深复制结果，不修改输入。已批准或已拒绝的草稿不再接受本函数处理。
- 选择：先实现独立函数，可直接验证每条规则；将决策逻辑直接塞入 interrupt 节点会使状态恢复与业务规则混在同一步。
- 产物：app/work_order_review.py、tests/test_work_order_review.py，以及本任务说明。
- 验收：approve/edit/reject、修改后再批准、未知/缺失字段、禁止编辑字段、原因校验、输入不变和独立列表。
- 命令：python -m pytest tests/test_work_order_review.py -q；然后 python -m pytest -q。
- 当前仅校验离线提供的决策数据并更新内存中的草稿；图暂停、恢复、决策历史持久化和正式工单写入留到后续。approved 并不表示已经创建正式工单。
