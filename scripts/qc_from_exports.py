#!/usr/bin/env python
"""从真实导出文件计算 QC / DQ，产出 qc_report.json + qc_report.html。

现场用法（需要先填 configs/lightnirs_columns.yaml）：

    python scripts/qc_from_exports.py \
        --eeg  /path/curry_export.cnt \
        --fnirs /path/lightnirs_export.csv \
        --fnirs-map configs/lightnirs_columns.yaml \
        --sync data/sync/sync_report.json \
        --out data/qc

无硬件预演（实验前一天演练整条链路）：

    python scripts/qc_from_exports.py --demo --out data/qc

EEG 读写：装了 MNE 时支持 .cdt/.cnt/.edf；也支持 .csv/.npy（先导出成 CSV 也能用）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from html import escape
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod  # noqa: E402
from bplus.features import (baseline_drift, count_scr, hrv_sdnn, line_noise_ratio,  # noqa: E402
                            motion_artifact_ratio, scalp_coupling_index)
from bplus.qc import compute_dq, score_eeg, score_epoch, score_fnirs, score_physiology, score_synchronization  # noqa: E402


# ----------------------------------------------------------------------------- loading
def load_eeg(path: Path) -> tuple[np.ndarray, float, list[str]]:
    """返回 (n_channels × n_samples, fs, channel_names)。"""
    suffix = path.suffix.lower()
    if suffix in {".csv"}:
        # 真实导出（CURRY/LIGHTNIRS）通常带表头；我们自己生成的演示文件没有 → 自动判断
        with path.open(encoding="utf-8-sig", errors="ignore") as fh:
            first = fh.readline()
        has_header = any(ch.isalpha() for ch in first)
        arr = np.loadtxt(path, delimiter=",", skiprows=1 if has_header else 0)
        arr = np.atleast_2d(arr)
        if arr.shape[0] > arr.shape[1]:        # 列数多于行数 → 说明是"1 通道 × N 采样"，需要转置
            arr = arr.T
        return arr, float("nan"), [f"ch{i+1}" for i in range(arr.shape[0])]
    if suffix in {".npy"}:
        arr = np.load(path)
        return (arr if arr.ndim == 2 else arr[None, :]), float("nan"), []
    try:
        import mne
    except ImportError as exc:                       # pragma: no cover - 现场环境相关
        raise SystemExit("需要 MNE 读取 CURRY/Neuroscan 文件：\n"
                         "    uv pip install mne curryreader\n"
                         "  或先在 CURRY 里导出为 CSV（本脚本支持 .csv/.npy）。") from exc
    if suffix in {".cdt", ".dap", ".dat"}:
        raw = mne.io.read_raw_curry(str(path), preload=True, verbose="ERROR")
    elif suffix == ".cnt":
        raw = mne.io.read_raw_cnt(str(path), preload=True, verbose="ERROR")
    elif suffix == ".edf":
        raw = mne.io.read_raw_edf(str(path), preload=True, verbose="ERROR")
    else:
        raise SystemExit(f"不支持的 EEG 后缀 {suffix}（支持 .cdt/.cnt/.edf/.csv/.npy）")
    return raw.get_data(), float(raw.info["sfreq"]), list(raw.ch_names)


def load_fnirs(path: Path, mapping: dict) -> dict:
    """按列映射读取 LIGHTNIRS 导出（**不猜列名**）。"""
    missing = [k for k in ("time_column", "hbo_columns") if not mapping.get(k)]
    if missing:
        raise SystemExit("LIGHTNIRS 列映射未填写：" + ", ".join(missing) +
                         "\n  请先编辑 configs/lightnirs_columns.yaml（现场打开一次导出文件即可看清列名）")
    with path.open(newline="", encoding="utf-8-sig", errors="ignore") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} 没有数据行")
    cols = set(rows[0])
    for key in ("time_column", "marker_column", "hbo_columns", "hbr_columns"):
        val = mapping.get(key)
        names = val if isinstance(val, list) else ([val] if val else [])
        unknown = [n for n in names if n and n not in cols]
        if unknown:
            raise SystemExit(f"列映射里的 {key} 在文件里找不到：{unknown}\n  文件实际列（前 12 个）：{list(cols)[:12]}")

    def col(name):
        return np.array([float(r[name]) for r in rows if r.get(name) not in (None, "")])

    hbo = np.mean([col(c) for c in mapping["hbo_columns"]], axis=0) if mapping["hbo_columns"] else None
    hbr = np.mean([col(c) for c in mapping.get("hbr_columns") or []], axis=0) if mapping.get("hbr_columns") else None
    raw_a = np.mean([col(c) for c in mapping.get("raw_760_columns") or []], axis=0) if mapping.get("raw_760_columns") else None
    raw_b = np.mean([col(c) for c in mapping.get("raw_850_columns") or []], axis=0) if mapping.get("raw_850_columns") else None
    marker = None
    if mapping.get("marker_column"):
        marker = [r.get(mapping["marker_column"]) for r in rows]
    return {"hbo": hbo, "hbr": hbr, "raw_760": raw_a, "raw_850": raw_b, "marker": marker,
            "time": col(mapping["time_column"]), "n_rows": len(rows)}


def compute_eeg_qc(data: np.ndarray, fs: float) -> dict:
    """可用通道率 / 工频比 / 伪迹率 / 坏窗率（§41）。"""
    if data.ndim == 1:
        data = data[None, :]
    per_ch_std = np.std(data, axis=1)
    amp = np.percentile(np.abs(data), 99, axis=1)
    usable = np.mean((per_ch_std > 1e-9) & (amp < 500.0))          # 平/饱和通道判废
    ref = data[np.argmax(per_ch_std)] if data.shape[0] else data[0]
    ln = line_noise_ratio(ref, fs) if np.isfinite(fs) else float("nan")
    artifact_ratio = float(np.mean(np.abs(data) > 5 * np.std(data))) if data.size else 1.0
    win = max(1, int(2 * fs)) if np.isfinite(fs) else len(ref)
    n_win = max(1, len(ref) // win)
    pp = np.array([np.ptp(ref[i * win:(i + 1) * win]) for i in range(n_win)])
    bad_window_ratio = float(np.mean(pp > 200.0))
    return {"usable_channel_ratio": float(usable), "line_noise_ratio": float(ln) if np.isfinite(ln) else 0.0,
            "movement_artifact_ratio": artifact_ratio, "epoch_rejection_ratio": bad_window_ratio}


def build_report(features: dict, sync: dict | None) -> tuple[dict, str]:
    qc_cfg = cfg_mod.load_yaml("qc.yaml")
    eeg = score_eeg(**features["eeg_qc"], cfg=qc_cfg)
    f = features["fnirs_qc"]
    fnirs = score_fnirs(sci=f.get("sci") if f.get("sci") is not None else 0.0,
                        channel_quality=f.get("channel_quality", 0.9),
                        motion_artifact_ratio=f.get("motion_artifact_ratio", 0.0),
                        baseline_drift=f.get("baseline_drift", 0.0), cfg=qc_cfg)
    epoch = score_epoch(valid_epoch_ratio=features["epoch"]["valid_ratio"],
                        n_epochs_per_condition=features["epoch"]["n_per_condition"], cfg=qc_cfg)
    sync_sub = score_synchronization(
        pulse_completeness=bool(sync and not sync.get("missing_codes")
                                and (sync.get("counts") or {}).get("fnirs", 0) > 0),
        offset_ms=(sync or {}).get("offset_ms"), jitter_sd_ms=(sync or {}).get("jitter_sd_ms"),
        verdict=(sync or {}).get("verdict", "INCONCLUSIVE"), cfg=qc_cfg)
    phys = features.get("physiology")
    physio = score_physiology(**phys, cfg=qc_cfg) if phys else None
    dq = compute_dq(eeg=eeg, fnirs=fnirs, epoch=epoch, sync=sync_sub, physiology=physio, cfg=qc_cfg)

    actions = []
    for name, sub in (("EEG", eeg), ("fNIRS", fnirs), ("Epoch", epoch), ("同步", sync_sub)):
        if sub.label in ("POOR", "INVALID"):
            actions.append(_ACTION.get(name, f"检查 {name} 分项"))
    if physio is None:
        actions.append("本次未采集生理信号：确认是设备未接还是遗漏（DQ 已重新归一化权重）")
    report = {"dq": dq.as_dict(), "subscores": {"eeg": eeg.__dict__, "fnirs": fnirs.__dict__,
                                                "epoch": epoch.__dict__, "synchronization": sync_sub.__dict__,
                                                "physiology": (physio.__dict__ if physio else None)},
              "actions": actions, "evidence_status": "PILOT_REQUIRED（阈值非国际标准）"}
    html = _html(report)
    return report, html


_ACTION = {
    "EEG": "检查电极阻抗/参考/接地；确认 50 Hz 工频来源（是否接了地线）；剔除坏导后重算",
    "fNIRS": "检查光极耦合（SCI 低）与头动；确认运动伪迹阈值是否需按采样率调整",
    "Epoch": "减少眨眼/头动；检查刺激是否被伪迹污染；必要时增加试次",
    "同步": "回到阶段 1 重跑 10 脉冲测试；检查分路器/极性/脉宽",
}


def _html(report: dict) -> str:
    dq = report["dq"]
    color = {"GOOD": "#16a34a", "ACCEPTABLE": "#0ea5e9", "POOR": "#f59e0b", "INVALID": "#dc2626"}[dq["band"]]
    rows = "".join(f"<tr><td>{escape(k)}</td><td>{v['score'] if v else '—'}</td>"
                   f"<td>{escape(str(v['label']) if v else '未采集')}</td></tr>"
                   for k, v in report["subscores"].items())
    acts = "".join(f"<li>{escape(a)}</li>" for a in report["actions"]) or "<li>无：全部达标</li>"
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>QC 报告</title>
<style>body{{font:15px/1.7 -apple-system,"PingFang SC",sans-serif;margin:0;background:#f7f8fa}}
.wrap{{max-width:820px;margin:0 auto;padding:26px}}.card{{background:#fff;border-radius:12px;padding:20px;margin:14px 0;
box-shadow:0 1px 3px rgba(0,0,0,.06)}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;padding:8px}}
.big{{font-size:30px;font-weight:700;color:{color}}}</style>
<div class="wrap"><h1>PILOT-0 · 数据质量报告</h1>
<div class="card"><p class="big">{dq['score']} · {dq['band']}</p>
<p class="muted">阈值均为 PILOT_REQUIRED 工程初值，不得写成国际标准。</p>
<table><tr><th>分项</th><th>分数</th><th>等级</th></tr>{rows}</table></div>
<div class="card"><h2>需要现场动作</h2><ul>{acts}</ul></div>
<div class="card"><h2>备注</h2><ul>{''.join(f'<li>{escape(n)}</li>' for n in dq.get('notes', []))}</ul></div>
</div></html>"""


# ----------------------------------------------------------------------------- demo
def make_demo_exports(out_dir: Path) -> tuple[Path, Path]:
    """无硬件预演：用合成数据生成"像真实导出"的 EEG/fNIRS CSV。"""
    from bplus.simulate import generate_session

    ev = {"deviant_onsets_s": [10 + 3 * i for i in range(60)],
          "standard_onsets_s": [10 + 3 * i + j for i in range(60) for j in (1.0, 2.0, 0.5)]}
    s = generate_session(400, mmn_events=ev, group="healthy_like", seed=3,
                         task_blocks=[(200, 60, 0.5)], task_amp=0.5)
    out_dir.mkdir(parents=True, exist_ok=True)
    eeg_csv = out_dir / "demo_eeg.csv"
    np.savetxt(eeg_csv, s.eeg[: int(60 * s.eeg_fs)].reshape(1, -1), delimiter=",", fmt="%.4f")
    fnirs_csv = out_dir / "demo_lightnirs.csv"
    with fnirs_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Time(s)", "CH1 Oxy-Hb", "CH2 Oxy-Hb", "CH1 Deoxy-Hb", "CH1 raw760", "CH1 raw850", "Mark"])
        for i in range(len(s.hbo)):
            w.writerow([f"{i / s.fnirs_fs:.4f}", f"{s.hbo[i]:.5f}", f"{s.hbo[i] * 0.9:.5f}",
                        f"{s.hbr[i]:.5f}", f"{s.raw_760[i]:.4f}", f"{s.raw_850[i]:.4f}", ""])
    (out_dir / "demo_lightnirs_columns.yaml").write_text(
        "sampling_interval_ms: 75\ntime_column: \"Time(s)\"\nmarker_column: Mark\n"
        "hbo_columns: [\"CH1 Oxy-Hb\", \"CH2 Oxy-Hb\"]\nhbr_columns: [\"CH1 Deoxy-Hb\"]\n"
        "raw_760_columns: [\"CH1 raw760\"]\nraw_850_columns: [\"CH1 raw850\"]\nn_channels: 2\n",
        encoding="utf-8")
    return eeg_csv, fnirs_csv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从导出文件计算 QC/DQ")
    ap.add_argument("--eeg")
    ap.add_argument("--fnirs")
    ap.add_argument("--fnirs-map", default="configs/lightnirs_columns.yaml")
    ap.add_argument("--eeg-fs", type=float, default=1000.0,
                    help="EEG 采样率（CSV 导出无法自描述，默认 1000 Hz；CURRY 导出请按实际填）")
    ap.add_argument("--sync", help="sync_report.json")
    ap.add_argument("--demo", action="store_true", help="用合成导出预演整条链路")
    ap.add_argument("--out", default="data/qc")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.demo:
        eeg_csv, fnirs_csv = make_demo_exports(out)
        args.eeg, args.fnirs = str(eeg_csv), str(fnirs_csv)
        args.fnirs_map = str(out / "demo_lightnirs_columns.yaml")
        sync = {"verdict": "PASS", "counts": {"eeg": 10, "fnirs": 10}, "missing_codes": [],
                "offset_ms": 12.0, "jitter_sd_ms": 8.0}
        print(f"[demo] 已生成合成导出：{eeg_csv.name} / {fnirs_csv.name}（含示例列映射）")
    else:
        if not args.eeg or not args.fnirs:
            ap.error("现场模式必须同时提供 --eeg 与 --fnirs（或使用 --demo）")
        sync = json.loads(Path(args.sync).read_text()) if args.sync and Path(args.sync).exists() else None
        if sync is None:
            print("⚠️ 未提供 --sync（sync_report.json）→ 同步分项按 INCONCLUSIVE 记 50 分")

    eeg_data, fs, ch_names = load_eeg(Path(args.eeg))
    if not np.isfinite(fs):
        fs = float(args.eeg_fs)
        print(f"提示：EEG 为 CSV（无采样率信息）→ 使用 --eeg-fs={fs:g} Hz")
    # 注意：这里必须按**文件系统路径**解析（cfg_mod.load_yaml 会在前面拼 configs/）
    import yaml as _yaml

    map_path = Path(args.fnirs_map)
    if not map_path.is_absolute() and not map_path.exists():
        map_path = Path(cfg_mod.CONFIG_DIR) / map_path.name
    mapping = _yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    fnirs = load_fnirs(Path(args.fnirs), mapping)

    fs_fnirs = (1000.0 / float(mapping["sampling_interval_ms"])) if mapping.get("sampling_interval_ms") else 13.333
    features = {
        "eeg_qc": compute_eeg_qc(eeg_data, fs if np.isfinite(fs) else 1000.0),
        "fnirs_qc": {
            "sci": (scalp_coupling_index(fnirs["raw_760"], fnirs["raw_850"], fs_fnirs)
                    if fnirs.get("raw_760") is not None and fnirs.get("raw_850") is not None else None),
            "channel_quality": float(1.0 - motion_artifact_ratio(fnirs["hbo"])),
            "motion_artifact_ratio": motion_artifact_ratio(fnirs["hbo"]),
            "baseline_drift": baseline_drift(fnirs["hbo"]),
        },
        "epoch": {"valid_ratio": float(1.0 - compute_eeg_qc(eeg_data, fs if np.isfinite(fs) else 1000.0)
                                       ["epoch_rejection_ratio"]),
                  "n_per_condition": 40},
        "physiology": None,
    }
    if features["fnirs_qc"]["sci"] is None:
        print("提示：导出文件里没有原始光强 → 无法计算 SCI（fNIRS 分项按 0 计，报告中会标注）")

    report, html = build_report(features, sync)
    (out / "qc_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                        encoding="utf-8")
    (out / "qc_report.html").write_text(html, encoding="utf-8")

    dq = report["dq"]
    print("=" * 76)
    print(f"DQ = {dq['score']} ({dq['band']})")
    for k, v in report["subscores"].items():
        if v:
            print(f"  {k:<16} {v['score']:>6.2f}  {v['label']}")
        else:
            print(f"  {k:<16}    —    未采集")
    if report["actions"]:
        print("需要现场动作：")
        for a in report["actions"]:
            print("  -", a)
    print(f"报告：{out/'qc_report.json'} / {out/'qc_report.html'}")
    return 0 if dq["band"] in ("GOOD", "ACCEPTABLE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
