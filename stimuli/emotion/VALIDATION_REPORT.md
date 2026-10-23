# Emotion 刺激库验证报告（VALIDATION_REPORT）

生成时间：2026-09-22T16:35:40

## 状态

- 刺激总数：24（{'positive': 8, 'neutral': 8, 'negative': 8}）
- REAL MODE：**DISABLED**
- 检查项：9/17 通过

## 检查明细

- [x] manifest_non_empty
- [x] files_exist
- [x] files_readable
- [x] sha256_matches
- [ ] technical_qc_passed
- [ ] duplicate_check_passed
- [x] licence_audited
- [x] source_traceable
- [ ] age_suitability_audited
- [ ] cultural_suitability_audited
- [ ] ethics_status_audited
- [ ] clinical_review_done
- [x] stimulus_balance_passed
- [ ] validation_report_completed
- [x] pilot_protocol_present
- [ ] clinical_team_approval
- [x] version_assigned

## 阻断项（未解决前禁止真实被试）

- 技术 QC 未通过：project_designed_synthetic_negative_negative_02, project_designed_synthetic_negative_negative_03, project_designed_synthetic_negative_negative_05, project_designed_synthetic_negative_negative_06, project_designed_synthetic_negative_negative_07, project_designed_synthetic_negative_negative_08, project_designed_synthetic_neutral_neutral_01, project_designed_synthetic_neutral_neutral_02 …
- 检测到重复刺激：[('project_designed_synthetic_negative_negative_02', 'project_designed_synthetic_negative_negative_01'), ('project_designed_synthetic_negative_negative_03', 'project_designed_synthetic_negative_negative_01'), ('project_designed_synthetic_negative_negative_05', 'project_designed_synthetic_negative_negative_01'), ('project_designed_synthetic_negative_negative_06', 'project_designed_synthetic_negative_negative_01'), ('project_designed_synthetic_negative_negative_07', 'project_designed_synthetic_negative_negative_01')]
- 年龄适配未通过：project_designed_synthetic_negative_negative_01, project_designed_synthetic_negative_negative_02, project_designed_synthetic_negative_negative_03, project_designed_synthetic_negative_negative_04, project_designed_synthetic_negative_negative_05, project_designed_synthetic_negative_negative_06, project_designed_synthetic_negative_negative_07, project_designed_synthetic_negative_negative_08
- 文化适配未通过：project_designed_synthetic_negative_negative_01, project_designed_synthetic_negative_negative_02, project_designed_synthetic_negative_negative_03, project_designed_synthetic_negative_negative_04, project_designed_synthetic_negative_negative_05, project_designed_synthetic_negative_negative_06, project_designed_synthetic_negative_negative_07, project_designed_synthetic_negative_negative_08
- 伦理状态未通过：project_designed_synthetic_negative_negative_01, project_designed_synthetic_negative_negative_02, project_designed_synthetic_negative_negative_03, project_designed_synthetic_negative_negative_04, project_designed_synthetic_negative_negative_05, project_designed_synthetic_negative_negative_06, project_designed_synthetic_negative_negative_07, project_designed_synthetic_negative_negative_08
- 临床审阅未通过：project_designed_synthetic_negative_negative_01, project_designed_synthetic_negative_negative_02, project_designed_synthetic_negative_negative_03, project_designed_synthetic_negative_negative_04, project_designed_synthetic_negative_negative_05, project_designed_synthetic_negative_negative_06, project_designed_synthetic_negative_negative_07, project_designed_synthetic_negative_negative_08
- VALIDATION_REPORT.md 尚未标记 STATUS: COMPLETE
- 缺少临床团队批准（CLINICAL_APPROVAL.md 未标记 APPROVED）

## 结论

STATUS: INCOMPLETE

> 本报告的阈值与判定均为 PROJECT 工程规则；授权结论以 emotion_sources.yaml 里的原文引用为准。