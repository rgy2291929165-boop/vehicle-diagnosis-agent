# 第三周 Day 1：无 LLM 三节点 LangGraph 练习

预计 2–3 小时。今天只做这个独立练习，不改现有 `/chat`，也不接真实模型、向量库或工具。

## 要理解的三个概念

- **State** 是节点间共享的数据结构；图执行时，各节点读取当前状态并返回需要更新的字段。没有 reducer 的字段默认被新值覆盖。`TypedDict` 表达字段形状，但不等于运行时参数校验。
- **Node** 是处理状态的函数。本练习每个节点只完成一步，不在节点内调用下一个节点。
- **Edge** 定义执行顺序。`START`、三个节点、`END` 构成一条固定路径；`compile()` 后用 `invoke()` 执行。

参考：[LangGraph 安装](https://docs.langchain.com/oss/python/langgraph/install)、[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。

## 亲手完成

1. 在 `vehicle-agent` 环境安装 `langgraph`，确认能导入 `StateGraph`，再把实际安装版本固定进 `requirements.txt`。保留安装版本和命令的实验记录。
2. 在 `app/graph_basics.py` 中用 `TypedDict` 定义最小状态：原始 `question`、规范化 `query`、`evidence`、`answer`、`trace`。实现 `normalize_question`、`lookup_mock`、`format_result` 三个节点，并连成 `START → normalize_question → lookup_mock → format_result → END`。对外提供 `build_graph()`，返回已编译、可 `invoke()` 的图；测试使用这个入口。
3. `lookup_mock` 只查内存中的固定示例：问题含“绝缘”时返回一条带 `chunk_id` 和 `text` 的模拟证据；其他问题返回空列表。`format_result` 只根据模拟证据生成固定文案；无证据时说明资料不足，不编造维修步骤。每个节点把自己的名字追加到 `trace`，通过返回新字段更新状态。
4. 新建 `tests/test_graph_basics.py`。至少测试：有证据输入的三个节点顺序、证据 ID 出现在结果里；无证据输入不生成具体维修步骤；`question` 保持原值而 `query` 去掉首尾空白。测试中不得使用网络或真实模型。
5. 在本文件末尾填写运行命令、LangGraph 版本、两次输入/输出摘要、测试结果，以及你对“节点返回部分状态”和“Edge 决定下一步”的一句话解释。

## 验收边界

- `python -m pytest tests/test_graph_basics.py -q` 通过，完整旧测试继续通过。
- 两个演示输入都能在有限的三节点路径后结束；输出包含完整 `trace`，且无证据情形不出现诊断步骤。
- 今天不要求补问、条件边、真实检索、模型、工具或持久化；这些在后续学习日逐项加入。

## 实验记录（完成后由学习者填写）

- 运行命令与 LangGraph 版本：
- 有证据输入/输出摘要：
- 无证据输入/输出摘要：
- 测试结果：
- 我对 State/Node/Edge 的解释：
- 遇到的错误及处理：
