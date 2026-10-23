# 授权结论与红线（LICENSES）

> 结论口径：`PUBLIC_VERIFIED` = 本轮实际访问官方页面/Zenodo API 读到授权原文；
> `UNVERIFIED` / `LICENSE_NONE` / `THIRD_PARTY_MIRROR_CLAIM` = **一律不可使用**（§5、§8）。

## 一、汇总

| 数据库 | 授权状态 | 能否用于科研 | 能否再分发 | 结论 |
| --- | --- | --- | --- | --- |
| **UIBVFEDPlus-Light**（虚拟面孔，DOI 10.1371/journal.pone.0287006） | CC-BY-4.0 | ✅ | ✅（需署名） | ✅ **可入库**；属虚拟面孔，须作为独立刺激类型验证（§40） |
| **UIBVFED Physical States**（Zenodo 10793613） | CC-BY-4.0 | ✅ | ✅ | ✅ 可入库 |
| **KDEF / AKDEF** | 研究、非商业 | ✅ | ❌ **明令禁止再分发** | ⚠️ 只能放 `restricted/`（gitignore），不得进仓库/公开代码 |
| **FACES（MPG, Ebner）** | 免费科研，逐案审批 | ✅（需申请账号 + 签协议） | ❌ 未授权 | ⚠️ 先申请；材料放 `restricted/` |
| **NimStim** | 官网本轮 403，无法核实 | — | — | ❌ 未核实 → 不可用，先联系作者 |
| **Chicago Face Database** | 官网本轮 406，无法核实 | — | — | ❌ 未核实 → 不可用 |
| **CK+（Zenodo 镜像自称 CC-BY-4.0）** | ⚠️ **授权链有问题** | — | — | ❌ **不可用**（见下方案例） |
| **JAFFE（Zenodo 副本）** | Zenodo license 字段 = **None** | — | — | ❌ 无许可证 → 默认保留所有权利 |
| **IAPS** | 需购买 | 需授权 | ❌ | ❌ 未购买前不可用 |
| **中文情绪面孔库（CFAPS/CAFPS 等）** | 本轮未检索到可核实的开放许可 | 需申请 | ❌ | ❌ 需联系版权方，或走自建路线 |
| **PROJECT_DESIGNED_SYNTHETIC**（本项目示意图） | 项目自建 | ✅（仅链路验证） | ✅ | ✅ 可入库；**标记 NOT_FOR_REAL_PARTICIPANTS** |

## 二、必须记住的案例：CK+ 的"镜像再许可"陷阱

Zenodo 上存在标题为 *CK+* 的记录（`10.5281/zenodo.11221351`），其 license 字段标为 **CC-BY-4.0**。
但 **CK+ 的原始授权来自匹兹堡大学（申请制，且限制再分发）**，镜像上传者**无权**替原作者再许可。

> 因此：**不能**因为某个镜像页写了 CC-BY 就认为可用。
> 必须回到**原始版权方**核对授权链。这类"授权链断裂"是本项目明令禁止的用法（§5、§8）。

## 三、KDEF 原文（本轮实读，2026-09-22）

> "The KDEF and AKDEF stimuli may be used only by researchers, and only for non-commercial purposes.
> The materials may never be redistributed in any form without written consent."

操作含义：
1. 可以用（科研、非商业）；
2. **不能**提交到 git、不能放进论文补充材料、不能上传到公开的代码仓库或数据集；
3. 只能放在 `stimuli/emotion/restricted/`（该目录已在 `.gitignore`）；
4. 论文中如需展示样例，必须按 KDEF 官网的 "Using and publishing" 规则办理。

## 四、FACES 原文（本轮实读）

> "FACES is freely available for usage in scientific research.
> Researchers can apply for an account on a case-by-case basis."
> "…please register for FACES and send the FACES Platform Release Agreement … to the FACES Technical Agent."

## 五、本项目自己的素材（PROJECT_DESIGNED）授权

由本项目脚本生成或拍摄/委托制作的刺激：
- 生成/拍摄记录、被拍摄者**肖像使用同意书**、伦理批件编号必须归档；
- 授权状态记为 `PROJECT_GENERATED`；
- 需要在 manifest 的 `notes` 里写明：同意书编号、批件编号、拍摄/生成日期。
