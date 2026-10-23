import json
import pytest

from bplus.eeg.cgx import analyze_cgx_brainvision, analyze_cgx_bundle, write_cgx_outputs


def _brainvision_triplet(root, *, n_samples=6000, sfreq=500):
    np = pytest.importorskip("numpy")
    pytest.importorskip("mne")
    header = root / "sample.vhdr"
    marker = root / "sample.vmrk"
    eeg = root / "sample.eeg"
    t = np.arange(n_samples) / sfreq
    data = np.column_stack([20e-6 * np.sin(2 * np.pi * 10 * t),
                            15e-6 * np.sin(2 * np.pi * 8 * t),
                            18e-6 * np.sin(2 * np.pi * 9 * t),
                            12e-6 * np.sin(2 * np.pi * 11 * t)]).astype("<f4")
    eeg.write_bytes(data.tobytes())
    marker.write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n[Common Infos]\n"
        "DataFile=sample.eeg\n[Marker Infos]\nMk1=Stimulus,1,100,1,\n",
        encoding="utf-8")
    header.write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n[Common Infos]\n"
        "Codepage=UTF-8\nDataFile=sample.eeg\nMarkerFile=sample.vmrk\nDataFormat=BINARY\n"
        "DataOrientation=MULTIPLEXED\nDataType=TIMEDOMAIN\nNumberOfChannels=4\n"
        f"DataPoints={n_samples}\nSamplingInterval={1e6/sfreq:g}\n[Binary Infos]\n"
        "BinaryFormat=IEEE_FLOAT_32\nUseBigEndianOrder=NO\n[Channel Infos]\n"
        "ch1=Fz,,1,V\nch2=Cz,,1,V\nch3=F3,,1,V\nch4=F4,,1,V\n", encoding="utf-8")
    return header


def test_cgx_import_writes_qc_and_does_not_invent_mmn(tmp_path):
    header = _brainvision_triplet(tmp_path)
    package = analyze_cgx_brainvision(header, participant_id="P01", session_id="1")
    assert package["sources"]["eeg"]["status"] == "VERIFIED"
    assert package["analysis"]["mmn"] is None
    assert package["analysis"]["eeg_import"]["qc"]["sampling_rate_hz"] == 500
    paths = write_cgx_outputs(package, tmp_path / "out")
    assert json.loads(paths["qc"].read_text())["format"] == "BrainVision"


def test_cgx_import_requires_all_companion_files(tmp_path):
    header = _brainvision_triplet(tmp_path)
    (tmp_path / "sample.eeg").unlink()
    with pytest.raises(FileNotFoundError, match="数据不完整"):
        analyze_cgx_brainvision(header, participant_id="P01", session_id="1")


def test_cgx_bundle_retains_complete_and_incomplete_recordings(tmp_path):
    complete = tmp_path / "complete"
    complete.mkdir()
    _brainvision_triplet(complete)
    broken = tmp_path / "broken"
    broken.mkdir()
    header = _brainvision_triplet(broken)
    (broken / "sample.eeg").unlink()
    package = analyze_cgx_bundle(tmp_path, participant_id="P01", session_id="1")
    bundle = package["data_quality"]["components"]["eeg_bundle"]
    assert bundle["headers_found"] == 2
    assert bundle["recordings_analyzed"] == 1
    assert bundle["recordings_rejected"] == 1
    assert package["analysis"]["eeg_bundle_errors"][0]["file"] == str(header)
