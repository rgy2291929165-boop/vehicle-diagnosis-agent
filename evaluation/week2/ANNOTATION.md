# Day 1：语料与问题标注

在 `corpus_manifest.csv` 核对现有记录并加入新的证据来源。`source` 应能指向可审查的资料；补充 `version`（出版/发布日期或资料版本）和 `provenance`（原始文件路径或 URL）。相同正文哈希的记录已标记为重复；清单目前只是审计记录，现有索引仍含重复，建立第二周基线时会按清单排除。原来的 demo 文本可作练习，不作为真实维修结论的权威证据。

在 `questions_draft.jsonl` 中每行写一个 JSON 对象。字段格式：

```json
{"id":"W2-001","question":"问题文本","answerable":true,"gold_document_ids":["文档ID"],"gold_evidence_quotes":["从该文档原文逐字复制的证据句"],"category":"direct","notes":""}
```

`gold_document_ids` 与 `gold_evidence_quotes` 按位置对应；一个问题允许多条证据。无证据题设 `answerable=false`，两个数组都为空。`category` 选 `direct`、`paraphrase`、`cross_section` 或 `no_evidence`。每个问题只考一个明确事实或判断，避免仅换词的重复问题；高压维修操作须忠实引用资料，不自行编造步骤。

今日完成标准：语料清单记录至少 12 个可定位的独立证据段；草稿达到 20 题，其中 16 题可回答、4 题无证据。所有正例证据必须能在对应文档正文中逐字找到。现已填入首批 8 篇官方资料的中文意译摘要和 20 题，核对记录见 `SOURCE_NOTES.md`。此文件仍是草稿，冻结测试集将在全部 60–100 题完成、去重并分层后，于调参前建立。
