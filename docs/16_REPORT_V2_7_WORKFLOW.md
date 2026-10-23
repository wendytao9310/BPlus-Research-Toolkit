# BPlus v2.7 报告工作流

## 两种报告状态

1. **实验完成待分析版**：实验结束后立即生成。只展示已经记录的行为结果；EEG、fNIRS、眼动、生理和访谈指标显示“待计算／数据不足”。
2. **正式审核版**：分析包通过 QC，并由研究者在“运行数据分析”窗口审核后生成。任何 QC=FAIL 的模块均隐藏数值并停止状态解释。

两种状态使用同一份固定桌面排版模板：

`src/bplus/reports/templates/participant_report_v2_7.html.j2`

模板只负责显示，不计算科研指标或判断状态。

## 程序界面

- **生成被试报告**：根据当前被试和会话生成或刷新报告。
- **运行数据分析**：导入 MMN、VFT 等处理结果，执行 QC，并在研究者审核后生成正式报告。
- **导入完整多模态分析包**：导入已经在外部完成的统一 JSON 分析包。

启动器必须填写被试编号、会话和年龄。年龄随会话保存到
`data/session/sub-被试_ses-会话_metadata.json`，后续重新生成报告时继续使用。

## 命令行

```bash
PYTHONPATH=src .venv-exp/bin/python -m bplus.report generate \
  --subject sub-TEST001 \
  --session ses-1
```

如果存在 `data/analysis/sub-TEST001_ses-1_analysis.json`，程序生成正式审核版；否则根据行为日志生成待分析版。

## 正式报告文件

```text
data/reports/multimodal/sub-TEST001_ses-1/
├── report.html
├── report_payload.json
├── metrics.json
├── metrics.csv
├── qc.json
├── provenance.json
├── participant_report.md
├── researcher_report.md
└── state_profile.json
```

`provenance.json` 保存报告版本、流程版本、Git 提交、配置哈希、生成时间和输入文件。任何进入 HTML 的数值均可追溯到分析包和 metrics 文件。

## 解释边界

- 报告不输出抑郁概率、诊断或“正常／异常脑功能”。
- `High / Moderate / Low` 只表示数据对研究结果的支持程度。
- 未建立并验证年龄匹配参考前，不显示“高于／低于同龄正常值”。
- 临床量表缺失时必须显示“未采集”，不得自动补值。
- 6–8 岁显示 K-SADS、CDRS-R 和 SDQ 家长版；9–11 岁增加 CDI、PHQ-15；
  12–18 岁显示 K-SADS、CDRS-R、PHQ-9 和 PHQ-15。该分层只决定报告显示哪些项目，
  不由程序解释临床含义。
- 从启动器、结果中心或命令行生成正式报告时必须存在研究者 `APPROVED` 审核记录。
- CURRY、LIGHTNIRS 和 aSee 原始文件仍需按已确认的设备导出格式处理；程序不会猜测厂家字段或事件映射。
