import csv
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import REQUIRED_COLUMNS, load_manifest
from scripts.analyze_emotion_pilot import THRESHOLDS, summarize, verdict
from scripts.emotion_enable_checklist import OWNER
from scripts.emotion_library import cmd_provenance, cmd_qc, cmd_scan, main as library_main
from scripts.emotion_review_sheet import CHECK_ITEMS, generate, merge

import types


def _tiny_library(root: Path, n_per_condition: int = 2) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(exist_ok=True)
    for cond in ("positive", "neutral", "negative"):
        for i in range(n_per_condition):
            img = Image.new("L", (64, 64), color=40 + i * 60)
            img.save(root / "raw" / f"{cond}_{i+1}.png")


def _args(**kw):
    return types.SimpleNamespace(**kw)


def test_scan_qc_and_review_merge_flow(tmp_path):
    root = tmp_path / "emotion"
    _tiny_library(root)
    assert cmd_scan(_args(root=str(root), dir=str(root / "raw"), source="PROJECT_DESIGNED_SYNTHETIC",
                          age_suitability="PENDING", cultural_suitability="PENDING",
                          ethics_status="PENDING", clinical_review="PENDING", version="v0")) == 0
    assert len(load_manifest(root)) == 6
    assert cmd_qc(_args(root=str(root), min_size=32, lum_min=0.05, lum_max=0.95, contrast_min=0.01)) == 0

    assert generate(root) == 0
    for rater in ("rater1", "rater2"):
        path = root / "review" / f"review_{rater}.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        for r in rows:
            for key, _ in CHECK_ITEMS:
                r[key] = "YES"
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["stimulus_id", "condition", "file"] + [k for k, _ in CHECK_ITEMS] + ["notes"])
            w.writeheader(); w.writerows(rows)
    assert merge(root, [root / "review/review_rater1.csv", root / "review/review_rater2.csv"]) == 0
    recs = load_manifest(root)
    assert all(r.age_suitability == "YES" and r.cultural_suitability == "YES" for r in recs)


def test_review_merge_keeps_conflicts_pending(tmp_path):
    root = tmp_path / "emotion"
    _tiny_library(root, 1)
    cmd_scan(_args(root=str(root), dir=str(root / "raw"), source="PROJECT_DESIGNED_SYNTHETIC",
                  age_suitability="PENDING", cultural_suitability="PENDING",
                  ethics_status="PENDING", clinical_review="PENDING", version="v0"))
    generate(root)
    for rater, val in (("rater1", "YES"), ("rater2", "NO")):
        path = root / "review" / f"review_{rater}.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        for r in rows:
            for key, _ in CHECK_ITEMS:
                r[key] = val
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["stimulus_id", "condition", "file"] + [k for k, _ in CHECK_ITEMS] + ["notes"])
            w.writeheader(); w.writerows(rows)
    merge(root, [root / "review/review_rater1.csv", root / "review/review_rater2.csv"])
    assert (root / "review" / "conflicts.csv").exists()
    assert all(r.age_suitability == "PENDING" for r in load_manifest(root))     # 不一致 → 保持 PENDING


def test_pilot_verdict_is_n_aware():
    good = {"condition": "negative", "valence_mean": 2.0, "clarity_mean": 4.5,
            "category_agreement": 0.7, "discomfort_ratio": 0.0, "n_raters": 3}
    ok, why = verdict(good)
    assert ok, why                                     # 3 人时 2/3 即可
    good_many = {**good, "n_raters": 20}
    ok2, why2 = verdict(good_many)
    assert not ok2 and any("0.80" in w for w in why2)  # 20 人时 0.70 < 0.80
    bad = {"condition": "negative", "valence_mean": 3.6, "clarity_mean": 2.0,
           "category_agreement": 0.9, "discomfort_ratio": 0.3, "n_raters": 20}
    ok3, why3 = verdict(bad)
    assert not ok3 and len(why3) >= 3


def test_pilot_summary_computes_means_and_agreement():
    rows = [{"stimulus_id": "s1", "condition": "positive", "category": "3", "valence": "5",
             "arousal": "4", "intensity": "4", "clarity": "5", "age_look": "2", "culture_fit": "4",
             "discomfort": "1"},
            {"stimulus_id": "s1", "condition": "positive", "category": "2", "valence": "4",
             "arousal": "3", "intensity": "3", "clarity": "4", "age_look": "3", "culture_fit": "5",
             "discomfort": "2"}]
    s = summarize(rows)["s1"]
    assert s["n_raters"] == 2 and s["valence_mean"] == 4.5
    assert s["category_agreement"] == 0.5 and s["discomfort_ratio"] == 0.5


def test_provenance_writes_ids_into_notes(tmp_path):
    root = tmp_path / "emotion"
    _tiny_library(root, 1)
    cmd_scan(_args(root=str(root), dir=str(root / "raw"), source="PROJECT_DESIGNED_SYNTHETIC",
                  age_suitability="PENDING", cultural_suitability="PENDING",
                  ethics_status="PENDING", clinical_review="PENDING", version="v0"))
    assert cmd_provenance(_args(root=str(root), ethics_id="ETH-1", consent_id="MC-9",
                                source=None)) == 0
    for r in load_manifest(root):
        assert "ethics_id=ETH-1" in r.notes and "consent_id=MC-9" in r.notes


def test_enable_checklist_maps_blockers_to_owners():
    keys = [k for k, _, _ in OWNER]
    for expected in ("技术 QC", "重复刺激", "年龄适配", "伦理状态", "临床团队批准"):
        assert any(expected in k for k in keys)


def test_repo_library_blocks_real_mode_via_cli():
    rc = library_main(["validate"])
    assert rc == 1                                     # 仓库现状必须是 DISABLED
