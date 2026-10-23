# Troubleshooting

- GUI 不启动：运行 `scripts/check_environment.py --profile launcher`，查看 `logs/launcher.log`。
- REAL 被阻止：这是预期的硬件 Gate；先完成 P0-4/P4-P7，不要修改代码绕过。
- Emotion 被阻止：刺激库未通过青少年 pilot/临床/伦理闸门。
- marker 缺失：停止招募；用 10 个校准码分别检查输出、EEG、fNIRS 导出。
- 图片找不到：检查 `stimuli/emotion/manifest.csv` 与实际路径，禁止临时从网络替换。
- PsychoPy 黑屏/音频失败：切回 DEMO，记录系统、显卡、音频设备和 PsychoPy 版本。

