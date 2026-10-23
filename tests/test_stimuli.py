import csv
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import (REAL_MODE_ERROR, REQUIRED_COLUMNS, assert_real_mode_allowed, check_balance,
                           find_duplicates, image_technical_qc, load_manifest, load_sources,
                           validate_library)
from bplus.stimuli.manifest import DEFAULT_ROOT

SOURCES = {"TEST_OK": {"id": "TEST_OK", "license_status": "CC_BY_4_0", "evidence": "TEST"}}


def _make_image(path: Path, *, seed: int = 0, size: int = 64) -> None:
    rng = np.random.default_rng(seed)
    arr = (rng.random((size, size)) * 180 + 30).astype("uint8")
    Image.fromarray(arr, mode="L").save(path)


def _write_manifest(root: Path, rows: list[dict]) -> None:
    with (root / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REQUIRED_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in REQUIRED_COLUMNS})


def test_empty_manifest_blocks_real_mode_with_the_exact_message():
    report = validate_library(DEFAULT_ROOT)
    assert report.ok is False
    assert report.error_message == REAL_MODE_ERROR
    with pytest.raises(RuntimeError) as exc:
        assert_real_mode_allowed(DEFAULT_ROOT)
    assert str(exc.value).splitlines()[0] == REAL_MODE_ERROR


def test_current_repo_library_is_registered_but_not_real_ready():
    """仓库里的 24 张示意图必须已被登记，但绝不允许插真实被试。"""
    records = load_manifest(DEFAULT_ROOT)
    assert len(records) >= 16
    assert {r.condition for r in records} == {"positive", "neutral", "negative"}
    allowed_sources = {"PROJECT_DESIGNED_SYNTHETIC", "UIBVFED_QUICKSTART"}
    assert {r.source_id for r in records} <= allowed_sources
    assert all(r.technical_qc in ("PASS", "FAIL") for r in records)
    rep = validate_library(DEFAULT_ROOT)
    assert rep.ok is False


def test_technical_qc_computes_hash_and_photometry(tmp_path):
    p = tmp_path / "a.png"
    _make_image(p, seed=1)
    q = image_technical_qc(p)
    assert q["width"] == q["height"] == 64
    assert 0.0 < q["luminance_mean"] < 1.0
    assert len(q["sha256"]) == 64 and len(q["ahash"]) == 256


def test_duplicate_detection_flags_identical_images():
    a = "0" * 256
    b = "0" * 256
    c = "1" * 256
    dupes = find_duplicates({"a": a, "b": b, "c": c}, max_distance=4)
    assert "b" in dupes and "c" not in dupes


def test_balance_check_reports_uneven_conditions():
    from bplus.stimuli.manifest import StimulusRecord

    recs = [StimulusRecord(stimulus_id=f"p{i}", condition="positive", file="x.png") for i in range(3)]
    recs += [StimulusRecord(stimulus_id=f"n{i}", condition="negative", file="x.png") for i in range(3)]
    rep = check_balance(recs, per_condition=3)
    assert rep["balanced"] is False and any("neutral" in i for i in rep["issues"])


def test_source_registry_marks_unsafe_licences(tmp_path):
    srcs = load_sources()
    assert srcs["CKPLUS_ZENODO_MIRROR"]["license_status"] == "THIRD_PARTY_MIRROR_CLAIM"
    assert srcs["CKPLUS_ZENODO_MIRROR"]["auto_download_allowed"] is False
    assert srcs["JAFFE_ZENODO"]["license_status"] == "LICENSE_NONE"
    assert srcs["KDEF"]["redistribution_allowed"] is False
    assert "may never be redistributed" in srcs["KDEF"]["quote"]
    assert srcs["UIBVFED_PLUS_LIGHT"]["license_status"] == "CC_BY_4_0"


def test_a_fully_validated_library_enables_real_mode(tmp_path):
    """构造一个"全部条件满足"的库 → 闸门必须放行（证明闸门不是永远说不）。"""
    root = tmp_path / "emotion"
    root.mkdir()
    rows = []
    for cond in ("positive", "neutral", "negative"):
        for i in range(2):
            name = f"{cond}_{i+1}.png"
            _make_image(root / name, seed=hash((cond, i)) % 10_000)
            q = image_technical_qc(root / name)
            rows.append({"stimulus_id": f"t_{cond}_{i+1}", "condition": cond, "file": name,
                         "sha256": q["sha256"], "width": q["width"], "height": q["height"],
                         "source_id": "TEST_OK", "license_status": "CC_BY_4_0",
                         "age_suitability": "YES", "cultural_suitability": "YES",
                         "ethics_status": "YES", "clinical_review": "YES",
                         "technical_qc": "PASS", "duplicate_of": "", "version": "v1",
                         "luminance_mean": round(q["luminance_mean"], 5),
                         "luminance_sd": round(q["luminance_sd"], 5),
                         "contrast_rms": round(q["contrast_rms"], 5)})
    _write_manifest(root, rows)
    (root / "PILOT_PROTOCOL.md").write_text("pilot", encoding="utf-8")
    (root / "VALIDATION_REPORT.md").write_text("STATUS: COMPLETE", encoding="utf-8")
    (root / "CLINICAL_APPROVAL.md").write_text("APPROVED by clinical team", encoding="utf-8")

    rep = validate_library(root, sources=SOURCES, per_condition=2)
    assert rep.ok is True, rep.blockers
    assert rep.checks["duplicate_check_passed"] and rep.checks["technical_qc_passed"]
    assert_real_mode_allowed(root, sources=SOURCES, per_condition=2)      # 不抛异常


def test_blocked_licence_state_is_rejected_even_if_everything_else_passes(tmp_path):
    root = tmp_path / "emotion"
    root.mkdir()
    _make_image(root / "a.png", seed=5)
    q = image_technical_qc(root / "a.png")
    _write_manifest(root, [{"stimulus_id": "x", "condition": "negative", "file": "a.png",
                            "sha256": q["sha256"], "width": 64, "height": 64, "source_id": "TEST_OK",
                            "license_status": "LICENSE_NONE", "age_suitability": "YES",
                            "cultural_suitability": "YES", "ethics_status": "YES",
                            "clinical_review": "YES", "technical_qc": "PASS", "version": "v1"}])
    (root / "PILOT_PROTOCOL.md").write_text("p", encoding="utf-8")
    (root / "VALIDATION_REPORT.md").write_text("STATUS: COMPLETE", encoding="utf-8")
    (root / "CLINICAL_APPROVAL.md").write_text("APPROVED", encoding="utf-8")
    rep = validate_library(root, sources=SOURCES, per_condition=1)
    assert rep.ok is False and any("授权状态" in b for b in rep.blockers)


def test_emotion_real_mode_is_blocked_but_demo_is_allowed():
    from bplus.gui.runner import run_session

    with pytest.raises(RuntimeError) as exc:
        run_session("emotion", "T99", "1", "/tmp/bplus_gate_test", dummy=False, mode="REAL")
    assert str(exc.value).startswith("ERROR: Emotion stimulus library is not validated")
    # PILOT 需要显式确认
    with pytest.raises(RuntimeError, match="pilot-staff"):
        run_session("emotion", "T99", "1", "/tmp/bplus_gate_test", dummy=False, mode="PILOT")
    # DEMO 必须放行
    res = run_session("emotion", "D99", "1", "/tmp/bplus_gate_test", dummy=True, mode="DEMO")
    assert len(res.trials) > 0
