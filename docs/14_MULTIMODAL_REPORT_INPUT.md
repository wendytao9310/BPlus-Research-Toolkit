# BPlus 多模态状态报告输入规范

启动器中的“导入多模态数据报告”读取一个 JSON 分析包，生成四页被试状态报告、研究者附录和可追溯 `state_profile.json`。

## 数据边界

- `VERIFIED`：真实导出、格式已验证且通过质量控制。
- `PILOT`：真实导出，但阈值或同步尚处于 Pilot 校准。
- `SIMULATED`：仅用于软件演示，不得作为被试结果。
- `MISSING`：未提供；对应状态显示“数据不足”。

输入模板：`configs/multimodal_report_input.example.json`。

## 特征名

### 行为

`nback.d_prime`, `nback.rt_cv`, `nback.accuracy`, `nback.omission_rate`,
`nback.false_alarm_rate`, `nback.median_rt_ms`, `emotion.valence_mean`,
`emotion.arousal_mean`.

### EEG

`eeg.mmn_amplitude_abs_uv`, `eeg.mmn_latency_ms`, `eeg.usable_channel_ratio`,
`eeg.line_noise_ratio`, `eeg.artifact_ratio`, `eeg.epoch_rejection_ratio`.

### fNIRS / NVC / 恢复

`fnirs.vft_hbo_delta_um`, `fnirs.nback_hbo_beta_um`, `fnirs.vft_hbo_block_sd`,
`fnirs.sci`, `fnirs.channel_quality`, `fnirs.motion_artifact_ratio`,
`fnirs.baseline_drift`, `nvc.r`, `nvc.p_value`, `nvc.lag_s`,
`recovery.hbo_return_ratio`.

### 眼动与临床

`eye.gaze_dispersion_deg`, `clinical.phq9_total`, `clinical.gad7_total`,
`clinical.sleep_score`, `clinical.social_impairment`.

## 设备原始文件

CURRY 可读路径是 `.cdt` 配套文件、`.cnt` 或 `.edf`。LIGHTNIRS 保留 `.OMM`，
并导出英文 `Hb&Abs`、全通道、平均点数 1 的文本。aSee Pro F250 需导出时间戳、
注视坐标、有效性和瞳孔数据。原始文件转特征的导入器只能在一次真实设备导出完成列名/事件验证后标记为 `VERIFIED`。

## 报告边界

报告是研究性状态描述，不是医学或心理诊断。问卷与访谈未经授权录入时，
程序不生成临床状态。LIGHTNIRS 数字输入只有 3 位（任务 1–7），必须使用独立的区块级映射，不得截断 BPlus 逻辑码。
