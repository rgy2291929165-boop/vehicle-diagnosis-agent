# 第四周：待审批工单草稿

- 负责人：学习者与教练。
- 前置：SQLite checkpoint 测试与跨进程恢复演示通过；全量基线 109 passed。
- 本步目标：从用户报告的故障信息生成独立草稿，不调用工具、不保存正式工单。
- 接口：`app.work_order_draft.build_work_order_draft(state: dict) -> dict`。
- 必填输入：非空字符串 vehicle_id、symptom，以及非空字符串列表 dtc_codes。
- 规范化：去除首尾空白，故障码转大写；不校验故障码是否在模拟工具目录中，保留人工复核所需的用户报告信息。
- 输出：vehicle_id、symptom、dtc_codes、title、description、status；状态固定为 pending_approval，标题为车辆故障人工复核。
- 草稿仅描述用户报告内容与人工复核请求。资料库无证据时仍允许生成复核草稿，不把工具建议或现有回答当作已验证诊断。
- 架构选择：先实现独立纯函数，便于学习与测试；后续作为独立审批图的节点调用。此时直接修改诊断图或增加工单数据库会混合多个尚未验收的步骤。
- 验收：正常输入与规范化、非法/缺失字段、输入不变与列表独立、无证据时不复制维修建议。
- 本步测试命令：`python -m pytest tests/test_work_order_draft.py -q`。
- 下一步：增加 approve/edit/reject 的人工决策校验，再接入 LangGraph interrupt 和 checkpoint；正式写入与幂等处理在后续单独验收。
