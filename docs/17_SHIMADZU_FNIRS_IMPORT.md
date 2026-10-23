# Shimadzu fNIRS 一键导入与结果报告

## 实验人员操作

1. 双击桌面的 `BPlus实验程序.app`。
2. 填写被试编号、会话编号、年龄和操作员。
3. 点击“导入近红外数据”。
4. 选择该被试的 Shimadzu 原始数据文件夹。程序自动寻找同一会话的
   `.OMM`、`.pat`、`.ext`、`.ain`，不会修改原始文件。
5. 查看自动显示的采样数、可用通道、有效 block 和 QC 状态。
6. 确认数据来源与 QC 后生成 HTML/PDF 科研状态报告。

普通实验人员无需导出 TXT，无需输入采样率、通道数、block、转换公式或
阈值。Voltage/Abs/Hb TXT 只用于开发回归。

## 当前已验证 Profile

- Profile：`shimadzu_interview_15_30_15_v1`
- 采样间隔：0.075 s（约 13.333333 Hz）
- 通道：20；波长：780/805/830 nm
- 事件：3=协议开始、16=访谈开始、32=访谈结束、1=block 结束
- 协议：15 s 前静息 + 30 s 访谈 + 15 s 后静息，共 30 blocks
- 当前 OMM 数据记录：big-endian，178 bytes/sample

其他 OMM 结构必须返回 `UNSUPPORTED_OMM_FORMAT`，不得套用本 profile 错误解析。

## 输出

每次导入写入：

`data/analysis/shimadzu/sub-<ID>_ses-<ID>/BPlus_Output/`

- `import_manifest.json`：只读源文件、大小和 SHA-256
- `qc.json`：文件、时序、通道、光学和 block QC
- `analysis_results.json`：block/channel/probe 级结果
- `report_payload.json`：v2.7 报告输入
- `multimodal_analysis_package.json`：现有报告链路分析包
- `report.pdf`：离线 PDF 报告（本机存在 Chrome/Chromium 时）

HTML 报告仍写入现有 `data/reports/multimodal/` 目录。

## 科学边界

- “relative” 表示复现 Shimadzu 连续 Hb 输出所得的相对变化量；未经设备文档
  确认时不擅自标记为 µM。
- 左右结果只称 Left/Right probe，不自动映射 DLPFC、VLPFC、mPFC 或 IFG。
- QC FAIL 或有效 block/通道不足时，指标为 `DATA_INSUFFICIENT`，不能用 0 代替。
- 报告仅用于科研，不构成医学诊断；不得自动输出抑郁概率、脑功能异常或健康判断。

## 回归证据（2026-10-13）

在本机同一会话的 24,000×20×3 官方导出上：

- Voltage 最大绝对误差：`4.99961852473696e-07`
- Abs 最大绝对误差：`6.047319924817884e-07`
- Hb 最大绝对误差：`7.326540185995101e-07`
- 所有 1,440,000 个值均在 `1e-6` 容差内
- 自动识别：24,000 samples、20 channels、30/30 valid blocks
- 当前综合 QC：WARN；19/20 channels usable
- 完整测试：145 passed

本条证据属于软件解析和本地数据回归，不等于医院现场硬件同步或临床有效性验证。
