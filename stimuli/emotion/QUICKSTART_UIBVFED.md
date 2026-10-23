# 快速起步：用 UIBVFED（CC-BY-4.0）先跑起来

**适用场景**：自建拍摄还没开始，但你已经需要一版**合法、可公开、可复现**的刺激先跑通流程与预实验。

---

## 1. 为什么选它

| 记录 | DOI | 授权 | 大小 | 用途 |
| --- | --- | --- | --- | --- |
| **Images for "Evaluating the Sensitivity to Virtual Characters"** | `10.5281/zenodo.399066` | **CC-BY-4.0** | **≈2.6 MB** | ✅ **快速起步首选**（几分钟下完） |
| UIBVFED: Virtual facial expression dataset | `10.1371/journal.pone.0231266` | CC-BY-4.0 | ≈1.7 GB | 需要更多身份/强度时 |
| UIBVFED Physical States | `10.5281/zenodo.10793613` | CC-BY-4.0 | ≈3.2 GB | 备选 |
| UIBVFEDPlus-Light（光照变体） | `10.1371/journal.pone.0287006` | CC-BY-4.0 | ≈33.6 GB | 未纳入快速起步（体积） |

**结论**：这三条都是**CC-BY-4.0 且 open access** → 允许使用与再分发（**必须署名**），是目前唯一能合法进仓库/公开数据集的现成情绪面孔库。
**代价**：它们是**3D 渲染的虚拟面孔**、表观年龄偏成人 → 必须登记为 `VIRTUAL_FACE`，且**必须按独立刺激类型验证**（任务 §40），不能假装等同真人面孔。

---

## 2. 三步走

```bash
cd work/mvp0

# ① 先看清单与授权（不下载）
python scripts/fetch_uibvfed.py --list

# ② 下载快速起步小集（约 2.6 MB；脚本会校验 md5）
python scripts/fetch_uibvfed.py --download --record quickstart

# ③ 解压 → 按条件映射（happy→positive / neutral→neutral / sad 等→negative）
unzip -o stimuli/emotion/raw/uibvfed/*.zip -d stimuli/emotion/raw/uibvfed/
python scripts/fetch_uibvfed.py --map
```

映射完成后登记进刺激库（**注意：全部审核字段先填 PENDING，REAL MODE 依然锁死**）：

```bash
python scripts/emotion_library.py scan \
    --dir stimuli/emotion/raw/uibvfed_mapped --source UIBVFED_QUICKSTART \
    --age-suitability PENDING --cultural-suitability PENDING \
    --ethics-status PENDING --clinical-review PENDING --version uibvfed-v1
python scripts/emotion_library.py qc
python scripts/emotion_library.py contacts
python scripts/emotion_library.py validate      # 仍然 DISABLED，除非走完全部审核
```

---

## 3. 必须署名（CC-BY 的硬性要求）

论文/海报/数据集说明里请使用**原库要求的引用**，至少包含：

> UIBVFED 数据集（作者团队），DOI: 10.5281/zenodo.399066 / 10.1371/journal.pone.0231266，许可：CC-BY-4.0。
> 本地刺激清单见 `stimulus_sources.csv`（`source_id = UIBVFED_QUICKSTART`），每张刺激的 `notes` 字段已记录 DOI。

**做法**：`scan` 时脚本会把 DOI 与署名要求写入每张刺激的 `notes`；论文方法部分引用 `stimulus_sources.csv` 即可。

---

## 4. 使用它的三个限制（必须在论文里写明）

1. **虚拟面孔 ≠ 真人面孔**：面孔加工对"真实感"敏感，虚拟面孔可能低估情绪强度；须作为**独立刺激类型**分析（`kind=VIRTUAL_FACE`）。
2. **表观年龄偏成人**：与 12–18 岁目标人群存在年龄错配；须在方法/局限中说明，或在 pilot 中评估年龄观感。
3. **文化适配未知**：UIBVFED 由西班牙团队制作，跨文化效价/唤醒度需本地 pilot 复核（`PILOT_PROTOCOL.md`）。

---

## 5. 与自建路线的关系

```
现在：UIBVFED（CC-BY）→ 跑通流程 + 预实验 + 建立分析管线
同时：按 ACQUISITION_SPEC.md 推进自建中国青少年面孔（伦理 + 拍摄 + 标准化）
最终：自建版本作为**正式刺激库**，UIBVFED 作为**可公开复现的对照/备选**
```

两条路线可以共存：`manifest.csv` 的 `source_id` 区分它们，分析时按 `kind` 分层报告。
