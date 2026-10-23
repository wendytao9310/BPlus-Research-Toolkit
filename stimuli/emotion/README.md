# Emotion 刺激库（Emotion Stimulus Library）

本目录是 Emotion 范式的**刺激材料管理系统**，而不是一堆图片。它的作用是：
**让"能不能给真实青少年被试看"这件事变成一个可检查、可审计、不可绕过的开关。**

## 当前状态（诚实说明）

| 项 | 状态 |
| --- | --- |
| 已登记刺激 | **24 张项目自绘示意图**（positive/neutral/negative 各 8 张） |
| 来源 | `PROJECT_DESIGNED_SYNTHETIC`（非真人照片、非 AI 真人脸） |
| 用途 | **仅 DEMO / PILOT 链路验证** |
| 真实被试 | ❌ **禁止**（manifest 里标记 `NOT_FOR_REAL_PARTICIPANTS`） |
| REAL MODE | **DISABLED**（闸门会抛出指定错误） |

## REAL MODE 闸门

真实被试走 Emotion 之前，以下条件必须**全部**满足：

```
manifest 非空 · 文件存在可读 · SHA256 匹配 · 授权已审 · 来源可追溯
· 年龄适配 · 文化适配 · 伦理状态 · 临床审阅 · 技术 QC · 重复检查
· 平衡性 · PILOT 完成 · VALIDATION_REPORT 标记 STATUS: COMPLETE
· version 已分配 · CLINICAL_APPROVAL.md 标记 APPROVED
```

不满足时的行为（已在代码中实现）：

```
ERROR: Emotion stimulus library is not validated for real participant acquisition.
```

```bash
python scripts/emotion_library.py validate      # 查看哪一项没过
python scripts/run_session.py --paradigm emotion ... --real     # 会被闸门拦下
```

## 目录结构

```
stimuli/emotion/
├── README.md                  ← 本文件
├── manifest.csv               ← 刺激主清单（实验程序只读这个文件）
├── stimulus_sources.csv       ← 来源与授权登记（含原文引用）
├── stimulus_audit.csv         ← 逐张图的人工审核表
├── LICENSES.md                ← 授权结论与红线
├── AGE_CULTURAL_ETHICS.md     ← 年龄/文化/伦理审核清单
├── PILOT_PROTOCOL.md          ← 刺激预实验方案
├── VALIDATION_REPORT.md       ← 由脚本生成；通过后标记 STATUS: COMPLETE
├── library_validation.json    ← 机器可读的验证结果
├── raw/                       ← 原始下载/自建素材（已 gitignore）
├── processed/                 ← 统一尺寸/灰度/亮度归一化后的正式刺激
├── preview/                   ← contact sheet（人工审核）
├── rejected/                  ← 被否决的刺激（保留原因，便于审计）
└── scripts/                   ← 本目录相关的专用脚本（可选）
```

## 工作流

```bash
# 1) 拿到素材（只放 raw/，或 restricted/ 若授权禁止再分发）
python scripts/download_emotion_stimuli.py --source KDEF        # 受控：不允许时不下载，只打印办理步骤

# 2) 登记 + 技术 QC + 验证
python scripts/emotion_library.py scan  --dir stimuli/emotion/raw/synthetic --source PROJECT_DESIGNED_SYNTHETIC
python scripts/emotion_library.py qc
python scripts/emotion_library.py validate
python scripts/emotion_library.py contacts      # 生成 preview/emotion_contact_sheet.html/png
python scripts/emotion_library.py report        # 生成 VALIDATION_REPORT.md
```

## 三条素材路线（§0 的结论）

| 路线 | 说明 | 本项目建议 |
| --- | --- | --- |
| **A 公开标准化库** | 见 `LICENSES.md`：CC-BY 类可入库；研究专用类**只能放 restricted/** | 作为方法学基准 |
| **B 自建（PROJECT_DESIGNED）** | 招募/拍摄中国青少年面孔，走伦理审批 + 标准化 + pilot | **最终正式版的推荐路线** |
| **C 开放图库** | Wikimedia/Unsplash 等 | 仅备选；情绪效价未经标准化 |

## 红线（绝对不做）

- ❌ 从搜索引擎/社交媒体/影视截图抓图当正式刺激
- ❌ 在授权不明时"先用着"
- ❌ 依据第三方镜像页的 CC-BY 声明使用有原始授权限制的数据库（见 `LICENSES.md` 的 CK+ 案例）
- ❌ 在刺激库未通过验证时给真实被试呈现 Emotion 范式
