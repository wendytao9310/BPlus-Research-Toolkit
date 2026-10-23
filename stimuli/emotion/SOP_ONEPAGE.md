# Emotion 范式现场 SOP（一页版 · 给操作员）

> 拿不准就停。**任何审核字段没写 `YES` 之前，Emotion 不允许给真实被试看。**

## 0. 三个数字（先记住）

| 状态 | 含义 | 操作 |
| --- | --- | --- |
| `REAL MODE=ENABLED` | 刺激库全部审核通过 | 可给真实被试跑 |
| `REAL MODE=DISABLED` | 有阻断项 | **不可**给真实被试；可跑 DEMO/PILOT |
| `PILOT` + `--pilot-staff` | 仅操作员本人测设备 | 数据不得用于科研结论 |

**一句话检查**：`python scripts/emotion_library.py validate`

---

## 1. 实验前 10 分钟

| □ | 动作 | 命令 / 判断 |
| --- | --- | --- |
| □ | 刺激库状态 | `emotion_library.py validate` → 必须 `ENABLED`（真实被试） |
| □ | 被试已被告知可随时停止 | 口头确认 + 知情同意已签 |
| □ | ESC 可用 | 试按一次，确认能中止程序 |
| □ | 眼动/EEG/fNIRS 就绪 | 见总 SOP（本页只讲 Emotion 部分） |
| □ | 触发链路还活着 | 发 3 个脉冲，CURRY/LIGHTNIRS 各看到 3 个 |

## 2. 运行（两种入口）

```bash
# 只跑 Emotion（含刺激呈现 + 块末评分）
python scripts/session.py --paradigm emotion --participant P01 --session 1 --real --backend parallel

# 或整段 70 分钟协议里的 Emotion 段（由主控程序调用，参数一致）
```

- 呈现时长 / ITI / 块结构由 `configs/paradigms/emotion.yaml` 决定，**现场不要改**。
- 触发码：neutral=401 / positive=402 / negative=403 / 评分=411 / 块开始=412。

## 3. 被试侧对话（逐字脚本）

> "接下来会看一些表情图片，每张几秒钟。
> 每组图片结束后，请你用键盘 1–5 回答两个问题：愉快程度、激动程度。
> **如果任何时候觉得不舒服，说一声或者按 ESC，我们就立刻停下来。**"

## 4. 记录（每名被试必填）

| □ | 项 |
| --- | --- |
| □ | 开始/结束时间、被试编号（不发姓名） |
| □ | 是否中途中止（`emotion_abort`：时间戳 + 原因） |
| □ | 是否跳过负性条件（若跳过 → 记为 protocol deviation） |
| □ | 主观反馈（疲劳 1–5 / 难度 1–5 / 是否不适） |
| □ | 触发日志存在：`data/.../sub-<ID>_ses-1_triggers.csv` |

## 5. 异常处理（照做即可）

| 症状 | 立即动作 |
| --- | --- |
| 被试说"不舒服 / 不想继续" | **立即 ESC 中止** → 切静息画面 → 通知访谈者 → 记录 `emotion_abort` |
| 图片没显示 / 黑屏 | 记录时间点 → 中止该 block（不要重播同一张）→ 检查 `manifest.csv` 里的 `file` 路径 |
| 按键没反应 | 检查窗口焦点（点击画面）→ 仍不行则中止并记录 |
| 触发未进 EEG/fNIRS | 记录 → 该被试数据标记"Emotion 同步异常" → 按 `SYNCHRONIZATION_PROTOCOL.md` 处理 |
| 程序崩溃 | 不要重启到同一被试的同一 block；记录时间点，改用剩余 block 或整段重采 |

## 6. 结束后 5 分钟

| □ | 动作 |
| --- | --- |
| □ | 情绪恢复：中性/正性内容或静息 ≥60 s，确认被试状态平稳 |
| □ | 导出 CURRY / LIGHTNIRS 数据并备份 |
| □ | 记录 `emotion_abort`（若有）+ 客观观察 |
| □ | 若出现明显不适 → 通知访谈者/临床人员（不自行判断） |

---

**红线**：① 审核未过不得给真实被试看；② 不得擅自替换图片；③ 不得跳过"可随时停止"的告知；④ 出现明显不适必须在 5 分钟内通知临床人员。
