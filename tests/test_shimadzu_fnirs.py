from pathlib import Path

import numpy as np
import pytest

from bplus.fnirs import (FNIRSImportError, ShimadzuFolderImporter, absorbance_to_hb,
                         adc_to_voltage, analyze_interview, build_fnirs_analysis_package,
                         raw_to_absorbance)
from bplus.reports.v27 import build_report_payload


RAW_FOLDER = Path("/Users/taowenwen/Desktop/测试数据/fnir")
GOLDEN_FOLDER = Path("/Users/taowenwen/Desktop/fNIRS数据")
HAS_REAL = (RAW_FOLDER / "zhangzhengqi20260917_162551.OMM").exists()


def _read_export(data_type: str) -> np.ndarray:
    for path in GOLDEN_FOLDER.glob("*.txt"):
        lines = path.read_text(encoding="cp932", errors="replace").splitlines()
        header = next((line for line in lines if "Data Type" in line), "")
        if header.split("Data Type", 1)[-1].strip() != data_type:
            continue
        row = next(index for index, line in enumerate(lines) if line.lstrip().startswith("Time(sec)"))
        return np.loadtxt(lines[row + 1:], usecols=range(4, 64)).reshape(24000, 20, 3)
    raise AssertionError(f"No {data_type} golden export")


def test_adc_to_voltage():
    raw = np.array([0, 1, 65535], dtype=np.uint16)
    assert np.allclose(adc_to_voltage(raw), (raw.astype(float) + 0.5) * 20 / 65535)


def test_net_less_equal_zero():
    absorbance, valid = raw_to_absorbance(np.array([[10]], dtype=np.uint16),
                                          np.array([[[9, 10, 11]]], dtype=np.uint16))
    assert np.isnan(absorbance[0, 0, :2]).all()
    assert valid.tolist() == [[[False, False, True]]]


def test_abs_to_hb_reference_zeroing():
    absorbance = np.ones((3, 2, 3))
    hbo, hbr, hbt = absorbance_to_hb(absorbance)
    assert np.allclose(hbo[0], 0) and np.allclose(hbr[0], 0) and np.allclose(hbt, hbo + hbr)


@pytest.mark.skipif(not HAS_REAL, reason="anonymous Shimadzu regression session is local-only")
def test_parse_omm_header_time_axis_channel_count_and_30_blocks():
    raw = ShimadzuFolderImporter(RAW_FOLDER).load()
    assert raw.n_samples == 24000
    assert raw.n_channels == 20
    assert raw.sampling_interval == pytest.approx(0.075, abs=1e-9)
    assert raw.duration == pytest.approx(1799.925, abs=1e-6)
    assert len(raw.blocks) == 30
    assert all(block.qc_status == "PASS" for block in raw.blocks)


@pytest.mark.skipif(not HAS_REAL, reason="anonymous Shimadzu regression session is local-only")
@pytest.mark.parametrize("data_type,attribute,max_expected", [
    ("Voltage", "voltage", 5.1e-7), ("Abs", "absorbance", 6.1e-7), ("Hb", "hb", 7.4e-7)])
def test_omm_against_shimadzu_txt(data_type, attribute, max_expected):
    raw = ShimadzuFolderImporter(RAW_FOLDER).load()
    actual = np.stack([raw.hbo, raw.hbr, raw.hbt], axis=-1) if attribute == "hb" else getattr(raw, attribute)
    error = np.abs(actual - _read_export(data_type))
    assert np.nanmax(error) <= max_expected
    assert np.nanmax(error) <= 1e-6
    assert np.mean(error <= 1e-6) == 1.0


@pytest.mark.skipif(not HAS_REAL, reason="anonymous Shimadzu regression session is local-only")
def test_event_parser_and_report_payload_has_no_demo_values():
    raw = ShimadzuFolderImporter(RAW_FOLDER, subject_id="ANON001", session_id="1").load()
    assert [event["code"] for event in raw.events[:4]] == [3, 16, 32, 1]
    result = analyze_interview(raw)
    package = build_fnirs_analysis_package(raw, result, participant_id="ANON001", session_id="1")
    payload = build_report_payload(package)
    text = str(payload)
    assert result["features"]["interview_valid_blocks"] == 30
    assert "DEMO01" not in text and "1.9" not in text


def test_no_omm(tmp_path):
    with pytest.raises(FNIRSImportError) as caught:
        ShimadzuFolderImporter(tmp_path).load()
    assert caught.value.code == "NO_OMM"


def test_session_mismatch_missing_ain(tmp_path):
    (tmp_path / "session.OMM").write_bytes(b"not-an-omm")
    (tmp_path / "session.pat").write_text("[Section Study]\nloop=30\n", encoding="ascii")
    with pytest.raises(FNIRSImportError) as caught:
        ShimadzuFolderImporter(tmp_path).load()
    assert caught.value.code == "UNSUPPORTED_OMM_FORMAT"
