# SeetaPsych × BPlus 融合方案

## 1. 结论与定位

SeetaPsych v1.0 适合加入 BPlus，但应作为**视频派生的次要/探索性测量层**，而不是新的被试任务，也不替代现有 aSee Pro F250、ECG/PPG、EEG、fNIRS、量表或临床访谈。其价值是：用同一段同步视频生成表情概率、16 个 AU、效价/唤醒度、rPPG 心率，并可在完成本地标定后提供屏幕注视点。

推荐的主链路：

`范式呈现与触发 -> EEG/fNIRS/aSee/生理 + RGB 视频同步采集 -> 原始数据冻结 -> SeetaPsych 离线推理 -> 时间轴对齐 -> QC -> 特征汇总 -> 多模态统计`

不要在 PsychoPy 呈现线程中实时跑模型。这样可避免 GPU/CPU 抢占造成掉帧和触发抖动，也能锁定模型版本后重复分析。

## 2. 对现有范式的具体用法

| BPlus 环节 | 使用的 SeetaPsych 输出 | 预注册分析建议 |
| --- | --- | --- |
| 静息基线 | HR、效价/唤醒、AU、面部可见率 | 建立个体基线；不做诊断分类 |
| MMN | HR、眨眼/面部运动相关 AU 作为伪迹协变量 | 仅作 QC/协变量，不解释为听觉加工指标 |
| VFT | AU、效价/唤醒、HR | 与 HbO 任务-静息对比联合；控制说话导致的面部运动混杂 |
| N-back | AU、效价/唤醒、HR；经验证后的 gaze | 负荷条件内变化、遗漏/RT 的辅助解释 |
| Emotion | 表情概率、AU、效价/唤醒、HR；经验证后的 gaze | 重点模块：刺激锁定曲线、自评一致性、跨模态耦合 |
| 临床访谈 | AU、效价/唤醒、HR | 仅在伦理批准且问题时间戳可用时；报告问题内变化，不自动推断抑郁 |
| Recovery | 相对峰值的恢复斜率和半恢复时间 | 与 ECG/EDA/fNIRS 恢复指标联合 |

场景 gaze following 只适合拍摄“被试与访谈者同框”的社交互动研究；当前单人电脑范式不应默认开启。

## 3. 必须增加的采集与同步约束

1. 正面、稳定漫射光，自动曝光/白平衡在正式记录前锁定；最低 1280×720、30 fps。
2. 相机画面与声音按原始时间戳保存，禁止可变帧率导出；每次会话记录实际 FPS、掉帧数、分辨率和编码器。
3. 会话开始、每个范式开始和结束时产生可同时被视频或音频辨认、并进入 BPlus 触发日志的同步事件。优先 TTL/LED；次选短音频脉冲。
4. 面部占画面足够大，眼镜反光、遮挡、强侧光和大幅转头单独标记。
5. 原始视频属于生物特征敏感数据：知情同意、最小权限、加密存储、去标识化编号、保留/删除计划缺一不可。

## 4. 部署

建议在独立分析环境部署，不污染采集环境。

```bash
cd 01_项目代码
python -m venv .venv-seetapsych

# Windows PowerShell
.venv-seetapsych\Scripts\Activate.ps1

# macOS/Linux
source .venv-seetapsych/bin/activate

python -m pip install -e '.[seetapsych]'
seetapsych-manager download
seetapsych-manager show
```

先用 WebUI 对少量伦理获批的样例视频检查可用性：

```bash
seetapsych-webui --log INFO
```

首次准备模型和算法依赖：

```bash
python scripts/run_seetapsych.py data/raw/sub-P001_ses-1_camera.mp4 \
  --participant P001 --session 1 --out data/session --prepare
```

后续同一台分析机通常无需 `--prepare`：

```bash
python scripts/run_seetapsych.py data/raw/sub-P001_ses-1_camera.mp4 \
  --participant P001 --session 1 --out data/session
```

只有完成相机内参、相机-屏幕外参和被试层面的本地误差验证后，才加入 `--with-gaze`。输出包括逐帧、无损嵌套字段的 JSONL，以及方便质控/统计索引的扁平 CSV。

## 5. Pilot 验证门槛（启用前）

- 至少做 20–30 名覆盖目标年龄段、性别、眼镜和不同肤色/光照条件的技术 pilot；正式样本量应由目标误差界限与重复测量设计确定。
- HR：同步 ECG 或接触式 PPG；报告 MAE、RMSE、相关、Bland–Altman bias/LoA，并按头动和肤色分层。
- gaze：与 aSee Pro F250 同步；报告像素/视觉角误差、有效样本率、头姿/眼镜分层误差。未达预注册门槛时只保留 aSee 为主分析。
- affect/AU：双人 FACS 子集或可靠人工编码 + 刺激后自评；报告 ICC/加权 κ/相关及分类校准，不把模型概率直接当真实情绪。
- 时间同步：视频对 TTL/LED/音频锚点的中位绝对误差与 P95 误差必须在 pilot 中实测并写入 QC。
- 冻结版本：保存 Python、SeetaPsych、各子模块、配置和模型哈希；升级后必须重跑技术验证。

## 6. 论文证据边界

论文报告的是工具箱及各模块在公开/自建基准上的表现，不是针对“青少年抑郁 × EEG-fNIRS”人群和本实验条件的临床验证。论文也明确指出跨人群/设备/环境泛化、头动下 rPPG、屏幕 gaze 的个体差异与无个体标定误差仍需改进。因此：工具可引入，结论必须在本项目 pilot 后才能升级为确认性指标。
