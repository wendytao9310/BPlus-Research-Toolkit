# BPlus 当前部署状态（2026-09-26）

## [PASS] 已完成

- Git 仓库、Python 3.11 `.venv`、项目配置和自动测试可用。
- Rest、MMN、VFT、N-back、Emotion、Recovery 六个范式可在 DEMO 模式独立运行。
- 中央 marker 字典、行为/触发 CSV+JSONL、帧同步 `callOnFlip` 与 100 ms 脉宽策略已实现。
- 模拟同步自检、缺失 marker 检测、EEG/fNIRS 合成数据和 NVC 分析已实现。
- Emotion 刺激库具备授权、伦理、pilot 和 REAL-mode 闸门；SeetaPsych 离线适配层已接入。
- Operator/Developer GUI、一键 `.command`、环境检查和 session preflight 已加入。
- 隔离实验环境 `.venv-exp` 已完成：Python 3.11.16、PsychoPy 2026.2.4、pylsl 1.18.5、Streamlit 1.49.1 等锁定依赖已安装。
- 120 项自动测试全部通过；六个范式的软件 Dry Run 全部通过，验收输出位于 `results/software_dry_run/`。
- 当前磁盘剩余约 14 GiB：DEMO/PILOT 可运行；REAL 要求至少 20 GiB，清理空间前会被预检阻止。

## [WARNING] 部分完成

- `.venv` 仍保留为开发环境；GUI 默认优先使用已完成的 `.venv-exp`。SeetaPsych 继续使用独立离线环境，避免影响实验呈现时序。
- Emotion 只有测试/候选刺激；生成图片均为 `PILOT_ONLY`，正式材料尚未完成青少年评分和临床审批。
- Camera、aSee、CURRY、LIGHTNIRS 适配器已定义接口与状态，但厂商 SDK/导出路径尚未现场确认。
- `docs/hardware/P0-4-hardware-validation-plan.md` 存在用户当日未提交修改，本次部署不覆盖。

## [BLOCKED] 尚未完成

- P4 物理 TTL、P5 EEG 收码、P6 fNIRS 收码、P7 双设备同时收码。
- EEG 采样率、LIGHTNIRS 触发锁存、接口/电压/极性、aSee 时间戳路径的现场确认。
- 完整真实设备 Dry Run 和正式 Pilot。

## 当前 Gate

| Gate | 状态 | 说明 |
| --- | --- | --- |
| P0 环境 | WARNING | 实验依赖已通过；磁盘仅约 14 GiB，未达到 REAL 的 20 GiB 门槛 |
| P1 任务 | PASS | 六个范式 DEMO 可运行 |
| P2 Marker | PASS | 字典、映射、日志测试通过 |
| P3 LSL | WARNING | 代码存在；环境尚未安装 pylsl/回环验证 |
| P4 TTL | BLOCKED | 需要实验 PC 和触发硬件 |
| P5 EEG | BLOCKED | 需要 CURRY/SynAmps² |
| P6 fNIRS | BLOCKED | 需要 LIGHTNIRS |
| P7 同步收码 | BLOCKED | 需要完整接线 |
| P8 Dry Run | PASS/DEMO | 软件 Dry Run 可跑；硬件 Dry Run 未完成 |
| P9 Pilot | BLOCKED | P4-P8 真机 Gate 未通过 |

## 不要重装/不要升级

- 不要删除或重建现有 `.venv`；新实验环境使用 `.venv-exp`。
- 不要升级系统 Python 3.13/3.14；PsychoPy 固定使用 Python 3.11。
- 不要重复 clone 项目或覆盖用户未提交的硬件文档。
- 不要将物理 TTL/厂商 SDK 状态从 PENDING 改成 PASS，除非有导出文件和报告。

## 版本冲突风险

- PsychoPy 及音视频/OpenGL 依赖应与数据分析/SeetaPsych 隔离；SeetaPsych 建议单独环境。
- macOS 可做开发与 DEMO，但正式并口/驱动采集通常需要 Windows 实验 PC。
- Numpy/SciPy 升级可能影响 MNE、PsychoPy 和厂商 SDK，正式环境必须使用锁文件。
