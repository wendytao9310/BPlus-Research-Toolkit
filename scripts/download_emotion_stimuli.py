#!/usr/bin/env python
"""受控下载器：**只在来源明确允许自动下载时才执行**。

纪律（对应任务 §2/§37）：
  * 不访问需要登录/验证码/购买/人工授权的来源；
  * 不绕过访问控制；
  * 来源未在 configs/stimuli/emotion_sources.yaml 里登记 auto_download_allowed: true 时，
    本脚本**只打印人工办理步骤**，不下载任何文件。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import load_sources  # noqa: E402

MANUAL_STEPS = {
    "KDEF": "访问 kdef.se → 填写使用协议 → 收到下载链接；材料**不得再分发**，只能放 stimuli/emotion/restricted/（已 gitignore）。",
    "FACES_MPG": "在 faces.mpdl.mpg.de 申请个人账号（逐案审批）→ 签署 FACES Platform Release Agreement → 下载。",
    "NIMSTIM": "先联系作者确认授权范围（官网本轮不可访问），拿到书面许可后再登记。",
    "CHICAGO_FACE_DB": "在 chicagofaces.org 提交申请并签署协议；注意其对再分发的限制。",
    "CHINESE_FACE_DB": "直接联系国内版权方（如中科院心理所）申请；或以 PROJECT_DESIGNED 自建路线替代。",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="受控刺激下载（默认不下载）")
    ap.add_argument("--source", required=True, help="emotion_sources.yaml 里的 source id")
    ap.add_argument("--out", default="stimuli/emotion/restricted")
    args = ap.parse_args(argv)

    src = load_sources().get(args.source)
    if not src:
        print(f"未知来源 {args.source}；先登记到 configs/stimuli/emotion_sources.yaml"); return 2

    if src.get("auto_download_allowed") and src.get("license_status") in {"CC_BY_4_0", "CC0", "PUBLIC_DOMAIN"}:
        print(f"{args.source} 允许自动下载（licence={src['license_status']}）。")
        print("提示：本仓库不内置该来源的下载器实现；请按其官方 API/DOI 说明编写，"
              "并把下载到 raw/{source}/ 后运行 `emotion_library.py scan`。")
        return 0

    print(f"⛔ {args.source} 不允许自动下载。")
    print(f"   授权状态：{src.get('license_status')}")
    print(f"   依据/说明：{src.get('notes','')}")
    if src.get("quote"):
        print(f"   原文：{src['quote']}")
    print("\n   人工办理步骤：")
    print("   -", MANUAL_STEPS.get(args.source, "按该来源官方网站的申请流程办理，并保存书面许可。"))
    print(f"\n   获得许可后：把文件放 {args.out}/（该目录已 gitignore），"
          "并在 emotion_sources.yaml 里更新 evidence 与 redistribution_allowed。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
