# Deployment Acceptance — 2026-09-26

## 可直接使用的范围

- 双击项目根目录的 `BPlus Experiment.command` 启动操作员界面。
- DEMO 与 PILOT 软件路径可使用；每次开始前必须通过界面中的 Device / Preflight Check。
- 六个范式 Rest、MMN、VFT、N-back、Emotion、Recovery 已完成无硬件软件 Dry Run。
- `VISUAL_DEMO` 使用中文界面、Hiragino Sans GB 中文字体、SoundDevice/CoreAudio 音频后端和模拟触发；演示节奏为正式时间轴的 35%，仅用于操作培训与流程检查。

## 本次验收证据

- `.venv-exp`：Python 3.11.16。
- PsychoPy 2026.2.4、pylsl 1.18.5、Streamlit 1.49.1 可导入。
- `pytest -q`：120 passed。
- 六范式行为日志与触发日志：`results/software_dry_run/`。
- 机器可读环境报告：`results/environment_check.json`。

## 标准实验流程

1. 确认知情同意、被试编号、会话编号和操作员姓名。
2. 双击 `BPlus Experiment.command`。
3. 选择模式与范式；首次练习选择 DEMO。
4. 点击 Device / Preflight Check；存在阻断项时不得开始。
5. 点击 Start Experiment，运行期间不切换窗口或运行其他高负载程序。
6. 完成后确认出现 `Session completed successfully`。
7. 核对 `data/session/` 中行为 CSV、触发 CSV/JSONL 和 preflight JSON。
8. 按 `docs/08_QC_PROTOCOL.md` 完成 QC，并备份原始数据。

## 尚不能宣称完成的范围

- REAL 模式仍由预检阻止：当前磁盘约 14 GiB，低于 20 GiB 门槛。
- P4-P7 物理 TTL、EEG、fNIRS 及双设备同步必须在 Windows 实验 PC 与真实硬件上验证。
- Emotion 正式刺激仍需青少年评分、临床审批与伦理确认；当前材料不得用于正式科研结论。
- macOS 上的 VISUAL_DEMO 成功不等于正式实验验收。正式实验必须在目标 Windows 实验机完成显示器、音频延迟、TTL、电压/极性、EEG/fNIRS 收码、眼动校准和全流程假被试验证。
