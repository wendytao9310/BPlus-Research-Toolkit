# MMN / VFT 结果中心操作说明

## 作用范围

结果中心把 MMN、VFT 的实验记录接到 BPlus 状态报告，但不替代 CURRY、LIGHTNIRS 的采集和预处理。
所有输出均为研究性状态描述，不是抑郁症诊断，也不能替代医生访谈和量表判断。

## 操作流程

1. 完成实验并冻结原始数据、事件文件和行为文件。
2. 在 CURRY/经确认的 EEG 流程中完成伪迹处理和分段，导出 MMN 预处理 NPZ。
3. 在 LIGHTNIRS/经确认的 fNIRS 流程中完成光密度、HbO 转换、运动伪迹处理，导出 VFT HbO NPZ。
4. 由两名研究人员依据录音或逐字稿填写 VFT 计分表并核对。
5. 双击 BPlus 启动器，填写被试编号和会话，打开“MMN / VFT 结果中心”。
6. 依次导入 MMN、VFT HbO 和 VFT 计分表。三项质控全部通过后，由审核人批准并生成报告。

## MMN NPZ 数据契约

- `standard_epochs`：标准音 epoch，形状为 `epochs × channels × samples`，单位 μV。
- `deviant_epochs`：偏差音 epoch，形状同上，单位 μV。
- `times_ms`：每个采样点相对刺激开始的毫秒时间，必须覆盖 -100 至 250 ms。
- `channel_names`：通道名称；默认 ROI 使用 Fz、Cz，至少应存在一个。

程序记录偏差音减标准音差异波在 100–250 ms 的负峰幅度、绝对幅度和潜伏期，同时记录标准/偏差有效试次数、ROI 和质控结论。

## VFT HbO NPZ 数据契约

- `hbo`：通道 × 采样点，单位 μM。
- `fs`：采样率 Hz。
- `task_windows`：任务窗的 `[开始秒, 持续秒]` 数组。
- `rest_windows`：静息窗的 `[开始秒, 持续秒]` 数组。
- `channel_names`：可选的通道名称。

程序记录任务相对静息的 HbO 变化、通道间离散程度、有效通道比例和时长质控。VFT 语言表现通过单独 CSV 保存有效词、重复词、闯入词、逐字稿和审核人。

## 审核与报告边界

- 任一输入缺失或质控失败：状态为 `INCOMPLETE`，不能从结果中心批准正式报告。
- 研究者未审核：分析包为 `PENDING`，不能生成被试状态报告。
- 审核通过：保存 `data/analysis/sub-被试_ses-会话_analysis.json`，报告保存在 `data/reports/multimodal/`。
- 原始数值、质控细节和证据链只在研究者附录与审计 JSON 中显示；被试页只显示状态、置信度和数据质量。
- 当前 CURRY 与 LIGHTNIRS 的厂家原始格式映射仍需实验室用真实匿名导出验证，程序不会猜测通道或事件列。
