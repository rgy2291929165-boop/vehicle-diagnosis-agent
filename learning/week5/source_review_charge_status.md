# 来源证据卡：充电口红灯

日期：2026-10-18（Asia/Shanghai）。编写：教练按学习者“帮我完成”的明确要求代写。

状态：单条主张的来源/翻译文档核对通过；有限摘录已保存并校验，完整网页快照未取得，车型年份/修订范围仍有缺口；学习者理解已确认（2026-10-18）。本卡不代表 D2 整体验收通过。

## 1. 来源与定位

- 本地文档 ID：`w2-tesla-charge-status`；引用片段 ID：`w2-tesla-charge-status:0`。
- 本地摘要：`data/documents/w2-tesla-charge-status.json`。
- 原始页面标题：Model 3 Owner's Manual / Charging Instructions。
- 官方 URL：[Tesla Charging Instructions](https://www.tesla.com/ownersmanual/model3/en_us/GUID-BEE08D47-0CE0-4BDD-83F2-9854FB3D578F.html)。
- 章节：Charging Instructions → Charge Port Light → RED。
- 本次来源访问日期：2026-10-18，Asia/Shanghai；本卡与摘录整理时间：2026-10-18T11:42:34+08:00。访问日期不作为来源出版日期。
- 原文短句：[离线摘录的 RED 条目](../../evaluation/week5/sources/tesla_charge_status_20261018_excerpt.html#red)。仅摘录该短句，避免以长篇手册代替定位证据。

## 2. 适用范围：事实、线索与未知项

| 类别 | 当前记录 | 使用边界 |
|---|---|---|
| 页面已确认 | 标题标识 Model 3；本条正文为英文 | 支持来源身份与车型名称定位 |
| URL 线索 | `model3/en_us` | 指向美国英语入口；不单凭路径证明全部北美车辆适用 |
| 旧 metadata 声明 | `Model 3 Owner Manual 2024+, North America; retrieved 2026-09-14` | 是旧摘要标注，本次未独立证实所有 2024+ 年份或配置 |
| 本次仍未知 | 具体适用车型年份、手册修订号、红灯条目对应车辆软件版本、条目发布/更新日期 | 不填猜测值；不借用页面其他功能的软件版本或版权年份 |

因此，本卡可验证这条网页原文与本地摘要的对应关系，不能单独完成针对任意用户车辆的适用性授权。用户车辆范围不明时应补问或限定回答来源范围。

## 3. 中文理解与摘要对照

本条描述的三个意思是：检测到故障、充电停止、需要查看触摸屏警报。本地摘要的红灯句子完整保留这三个意思，没有新增确定的故障原因，核对结论为**一致**。

允许的回答限于这一资料支持的状态解释和提示。它不能证明高压电池、充电口、传感器等具体部件损坏，不能推出 P0AA6 或其他标准 DTC，也不支持拆装维修指令、确定根因或故障已经排除。

核对范围仅为红灯句子：没有将状态灯文档其余颜色、第二份警报文档或整体资料库记为本轮已审计。

## 4. 证据保存与 SHA-256

- 离线摘录：[tesla_charge_status_20261018_excerpt.html](../../evaluation/week5/sources/tesla_charge_status_20261018_excerpt.html)。
- 摘录 SHA-256：`bda8aeefb935d934367dc890121002134c5d1d97b239e92a20ed6739f67fccee`。
- 获取及文件清单：[tesla_charge_status_20261018_manifest.json](../../evaluation/week5/sources/tesla_charge_status_20261018_manifest.json)。
- HTTP 403 响应头：[tesla_charge_status_20261018_download_attempt_headers.txt](../../evaluation/week5/sources/tesla_charge_status_20261018_download_attempt_headers.txt)；仅证明下载失败，不作为正文来源。
- 本地摘要核对时 SHA-256：`47874503b688f4f6d659cff86eaa56698eadad11c6e6fa19222c8df9b3b3f1e5`。

复核命令（在主项目执行）：

```bash
shasum -a 256 evaluation/week5/sources/tesla_charge_status_20261018_excerpt.html
```

获取方式：网页工具读取官方页面；教练将原文短句、标题/URL、访问日和范围限制整理为本地独立 HTML。命令行原始页面下载被网站返回 403 拒绝，**未取得完整原始 HTML 或 PDF**。本地摘录可离线打开，但不是厂家原始快照或原始响应哈希；本卡及摘录均为教练整理的证据产物。

## 5. 验收与遗留问题

- 已完成：官方条目定位、单句主张核对、摘要对照、来源分类、有限摘录归档及哈希检查。
- 未完成：完整网页快照、精确车型年份/手册修订范围；继续如实保留缺口，不覆盖旧 metadata 或冻结文件。
- 未涉及：实车或设备采集、企业系统查询、模型新调用、业务代码修改、CP_a053/CP_a054 来源审核及约 20 条开发场景。
- 下一步仍先做学习者理解确认，不跳入新任务：**这条证据能说明红灯提示故障，为什么仍不能说明电池已经损坏？**


## 6. 学习者理解确认（2026-10-18）

学习者指出不能确定其他部件是否损坏，正确识别红灯不能定位损坏部件。教练补充：该证据只能支撑充电状态与查看警报，既不能确认电池损坏，也不能确认其他某个部件损坏。单条主张核对、有限摘录归档与理解确认通过；完整快照及精确适用范围仍为遗留，不据此声明 D2 全部完成。
