# Day 1 来源核对记录

核对日期：2026-09-14。新增 8 篇本地文档是对官方英文资料的**中文意译摘要**，不是厂家原文或正式维修工序。题目的 `gold_evidence_quotes` 精确指向这些本地摘要；下列原始页面用于核查摘要是否有出处。Tesla 内容限 Model 3 2024+ 北美版在线车主手册，网页可能随软件和地区更新；使用其他车型或地区时应重新核对。

| 本地文档 ID | 官方来源与核对位置 | 摘要所覆盖的事实 |
|---|---|---|
| `w2-tesla-charge-status` | [Tesla Charging Instructions](https://www.tesla.com/ownersmanual/model3/en_us/GUID-BEE08D47-0CE0-4BDD-83F2-9854FB3D578F.html)，Charge Port Light | 蓝、绿、琥珀、红色状态灯含义 |
| `w2-tesla-charge-alerts` | [Tesla Troubleshooting Alerts](https://www.tesla.com/ownersmanual/model3/en_us/GUID-9A3F0F72-71F4-433D-B68B-0A472A9359DF.html)，CP_a053、CP_a054 | 充电站通信/供电与锁扣警报 |
| `w2-tesla-battery-health` | [Tesla High Voltage Battery Health](https://www.tesla.com/ownersmanual/model3/en_us/GUID-B9807218-7291-4F68-9AFF-7C525CF498F3.html)，Running the Battery Health Test | 测试的供电、车辆状态和空调限制 |
| `w2-tesla-hv-components` | [Tesla Electric Vehicle Components](https://www.tesla.com/ownersmanual/model3/en_us/GUID-8FA15856-1720-440F-838B-ACFBA8D7D608.html)，High Voltage Components | 车主不可自行维护高压部件与线缆识别 |
| `w2-tesla-battery-info` | [Tesla High Voltage Battery Information](https://www.tesla.com/ownersmanual/model3/en_us/GUID-7FE78D73-0A17-47C4-B21B-54F641FFAEF4.html)，Battery Warnings and Cautions | 冷却液提示和电量降至 0% 后的风险 |
| `w2-tesla-normal-sounds` | [Tesla Normal Operating Sounds](https://www.tesla.com/ownersmanual/model3/en_us/GUID-AA58ED67-9C93-4EE6-8B19-9FDABE018787.html)，While Charging | 超充风扇与车底声音的常见原因 |
| `w2-tesla-hot-weather` | [Tesla Hot Weather Best Practices](https://www.tesla.com/ownersmanual/model3/en_us/GUID-6F5B7B3F-F020-471D-9D46-D1F990A6237A.html)，Charging | 使用行程规划提前准备电池温度 |
| `w2-nhtsa-flood-safety` | [NHTSA 811577 车主安全指引 PDF](https://www.nhtsa.gov/sites/nhtsa.gov/files/811577-interimguidehev-hv-batt_owner-v2.pdf)，Hazards、Vehicle Information | 浸水高压电池触电/起火风险及受损车辆服务边界 |
| `w2-tesla-cold-weather` | [Tesla Cold Weather Best Practices](https://www.tesla.com/ownersmanual/model3/en_mo/GUID-F907200E-A619-4A95-A0CF-94E0D03BEBEF.html)，Charge Port、Cold Battery | 锁扣冻结、低温电池图标与能力限制 |
| `w2-tesla-scheduled-charge` | [Tesla Scheduled Precondition and Charge](https://www.tesla.com/ownersmanual/model3/en_gb/GUID-76995CEC-6402-4BFF-99FA-CEFA36E64A19.html)，Create a Schedule、Preconditioning | 地点预约、快充限制与预处理行为 |
| `w2-tesla-submerged-vehicle` | [Tesla Submerged Vehicle Guidance](https://www.tesla.com/ownersmanual/2017_2023_model3/en_gb/GUID-5D2AF796-2052-4A24-9327-E3C0E2DB9B19.html)，Best Practices、Handling a Submerged Vehicle | 浸水前准备和浸水后安全边界 |
| `w2-tesla-charge-workflow` | [Tesla Charging Instructions](https://www.tesla.com/ownersmanual/model3/en_us/GUID-BEE08D47-0CE0-4BDD-83F2-9854FB3D578F.html)，Opening the Charge Port、Plugging In、Stopping Charging | 充电口位置、公共充电、插拔与高压液体风险 |

当前语料含 12 篇纳入文档和 60 道题，开发集与冻结测试集的 ID 见 `splits.json`。第一周 demo 资料缺乏可核验的原始出处，清单已标记为不纳入第二周正式语料；现有 Chroma 索引尚未按清单重建，故不能用它报告第二周检索分数。
