"""Read-only Shimadzu OMM importer for the validated 20-channel profile.

The binary layout is deliberately profile-gated. Unknown layouts fail closed
instead of being coerced into apparently valid scientific data.
"""
from __future__ import annotations

import configparser
import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

WAVELENGTHS = (780, 805, 830)
SHIMADZU_EXPORT_TOLERANCE = 1e-6
HB_MATRIX = np.array([
    [-1.48866679, 0.59702330, 1.48467662],
    [1.85452568, -0.23936042, -1.09465380],
])


class FNIRSImportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Block:
    index: int
    pre_start: int
    interview_start: int
    interview_end: int
    post_end: int
    sampling_rate: float
    complete: bool = True
    qc_status: str = "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "pre_start_sample": self.pre_start,
            "interview_start_sample": self.interview_start,
            "interview_end_sample": self.interview_end,
            "post_end_sample": self.post_end,
            "pre_start_s": self.pre_start / self.sampling_rate,
            "interview_start_s": self.interview_start / self.sampling_rate,
            "interview_end_s": self.interview_end / self.sampling_rate,
            "post_end_s": self.post_end / self.sampling_rate,
            "pre_duration_s": (self.interview_start - self.pre_start) / self.sampling_rate,
            "interview_duration_s": (self.interview_end - self.interview_start) / self.sampling_rate,
            "post_duration_s": (self.post_end - self.interview_end + 1) / self.sampling_rate,
            "complete": self.complete,
            "qc_status": self.qc_status,
        }


@dataclass
class FNIRSRaw:
    subject_id: str
    session_id: str
    source_files: dict[str, Path]
    sampling_rate: float
    sampling_interval: float
    time: np.ndarray
    reference_raw: np.ndarray
    raw_adc: np.ndarray
    voltage: np.ndarray
    absorbance: np.ndarray
    hbo: np.ndarray
    hbr: np.ndarray
    hbt: np.ndarray
    events: list[dict[str, Any]]
    blocks: list[Block]
    metadata: dict[str, Any]
    qc: dict[str, Any] = field(default_factory=dict)
    manufacturer: str = "Shimadzu"
    device_model: str = "Shimadzu fNIRS (profile-validated OMM)"
    wavelengths: tuple[int, int, int] = WAVELENGTHS

    @property
    def n_samples(self) -> int:
        return len(self.time)

    @property
    def n_channels(self) -> int:
        return self.raw_adc.shape[1]

    @property
    def duration(self) -> float:
        return float(self.time[-1]) if self.n_samples else 0.0


def adc_to_voltage(raw_adc: np.ndarray) -> np.ndarray:
    return (np.asarray(raw_adc, dtype=np.float64) + 0.5) * 20.0 / 65535.0


def raw_to_absorbance(reference_raw: np.ndarray, raw_adc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    reference = np.asarray(reference_raw, dtype=np.int64)[..., None]
    net = np.asarray(raw_adc, dtype=np.int64) - reference
    valid = net > 0
    absorbance = np.full(net.shape, np.nan, dtype=np.float64)
    absorbance[valid] = np.log10(32767.0 / net[valid])
    return absorbance, valid


def absorbance_to_hb(absorbance: np.ndarray, *, reference_zero: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = np.asarray(absorbance, dtype=np.float64)
    if data.ndim != 3 or data.shape[-1] != 3:
        raise ValueError("Absorbance must be samples x channels x 3 wavelengths")
    hb = np.einsum("scw,kw->sck", data, HB_MATRIX)
    hbo, hbr = hb[..., 0], hb[..., 1]
    if reference_zero:
        hbo = hbo - hbo[0]
        hbr = hbr - hbr[0]
    return hbo, hbr, hbo + hbr


def _read_pat(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="cp936", errors="replace")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    values: dict[str, str] = {}
    for section in parser.sections():
        for key, value in parser[section].items():
            values[key.lower()] = value.strip()
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ShimadzuFolderImporter:
    """Select one coherent session and import the validated Shimadzu OMM profile."""

    profile = "shimadzu_interview_15_30_15_v1"
    record_header_bytes = 18
    ain_record_bytes = 102

    def __init__(self, folder: str | Path, *, subject_id: str = "", session_id: str = "",
                 selected_stem: str | None = None):
        self.folder = Path(folder).expanduser().resolve()
        self.subject_id = subject_id
        self.session_id = session_id
        self.selected_stem = selected_stem

    def discover(self) -> tuple[dict[str, Path], list[str]]:
        if not self.folder.is_dir():
            raise FNIRSImportError("NO_OMM", "选择的近红外数据文件夹不存在")
        omm_files = sorted(self.folder.glob("*.OMM")) + sorted(self.folder.glob("*.omm"))
        if self.selected_stem:
            omm_files = [path for path in omm_files if path.stem == self.selected_stem]
        if not omm_files:
            raise FNIRSImportError("NO_OMM", "所选文件夹中未找到 OMM 原始文件")
        candidates = []
        for omm in omm_files:
            stem = omm.stem
            files = {"omm": omm}
            for suffix in ("pat", "ext", "ain"):
                exact = next(iter(self.folder.glob(f"{stem}.{suffix}")), None)
                if exact:
                    files[suffix] = exact
            ain_samples = files.get("ain").stat().st_size // self.ain_record_bytes if files.get("ain") else 0
            candidates.append((len(files), ain_samples, omm.stat().st_size, files))
        candidates.sort(key=lambda item: item[:3], reverse=True)
        files = candidates[0][3]
        missing = [name.upper() for name in ("pat", "ext", "ain") if name not in files]
        warnings = [f"未混入其他会话 OMM：{item[3]['omm'].name}" for item in candidates[1:]]
        if missing:
            warnings.append(f"会话辅助文件缺失：{', '.join(missing)}")
        return files, warnings

    def load(self) -> FNIRSRaw:
        files, discovery_warnings = self.discover()
        metadata = _read_pat(files["pat"]) if "pat" in files else {}
        n_channels = 20
        record_size = self.record_header_bytes + n_channels * 8
        n_samples = files["ain"].stat().st_size // self.ain_record_bytes if "ain" in files else 0
        if not n_samples:
            raise FNIRSImportError("UNSUPPORTED_OMM_FORMAT", "缺少可用于安全确定采样点数的同会话 AIN 文件")
        if files["ain"].stat().st_size % self.ain_record_bytes:
            raise FNIRSImportError("SESSION_MISMATCH", "AIN 文件长度不是已验证 102-byte 记录的整数倍")
        blob = files["omm"].read_bytes()
        data_start = len(blob) - n_samples * record_size
        if data_start < 0:
            raise FNIRSImportError("UNSUPPORTED_OMM_FORMAT", "OMM 文件不足以容纳同会话 AIN 所指示的采样数")

        times = np.empty(n_samples, dtype=np.float64)
        flags = np.empty((n_samples, 4), dtype=np.uint16)
        raw = np.empty((n_samples, n_channels, 4), dtype=np.uint16)
        view = memoryview(blob)
        for index in range(n_samples):
            record = view[data_start + index * record_size:data_start + (index + 1) * record_size]
            times[index] = struct.unpack(">d", record[:8])[0]
            flags[index] = np.frombuffer(record[8:16], dtype=">u2")
            detected = int.from_bytes(record[16:18], "big")
            if detected != n_channels:
                raise FNIRSImportError("INVALID_CHANNEL_COUNT", f"第 {index + 1} 个样本的通道数为 {detected}，期望 {n_channels}")
            raw[index] = np.frombuffer(record[18:], dtype=">u2").reshape(n_channels, 4)

        diffs = np.diff(times)
        if not np.all(np.isfinite(times)) or abs(times[0]) > 1e-9 or np.any(diffs <= 0):
            raise FNIRSImportError("TIME_AXIS_ERROR", "OMM 时间轴无效或非严格递增")
        interval = float(np.median(diffs))
        if not np.isclose(interval, 0.075, atol=1e-6):
            raise FNIRSImportError("UNSUPPORTED_OMM_FORMAT", f"未验证的采样间隔：{interval:.9f} s")

        reference = raw[..., 0]
        adc = raw[..., 1:]
        voltage = adc_to_voltage(adc)
        absorbance, optical_valid = raw_to_absorbance(reference, adc)
        hbo, hbr, hbt = absorbance_to_hb(absorbance)
        events = self._events(flags, times)
        protocol = self._protocol_durations(metadata)
        blocks = self._blocks(events, 1.0 / interval, protocol)
        qc = self._qc(files, times, adc, voltage, absorbance, hbo, hbr, blocks,
                      optical_valid, discovery_warnings, metadata)
        subject = self.subject_id or metadata.get("patid") or metadata.get("patname") or files["omm"].stem
        return FNIRSRaw(subject, self.session_id or files["omm"].stem, files, 1.0 / interval, interval,
                        times, reference, adc, voltage, absorbance, hbo, hbr, hbt, events, blocks,
                        {**metadata, "profile": self.profile, "data_start": data_start}, qc)

    def load_all(self) -> tuple[list[FNIRSRaw], list[dict[str, str]]]:
        """Read every coherent OMM session in the selected folder, never only the largest one."""
        omm_files = sorted(self.folder.glob("*.OMM")) + sorted(self.folder.glob("*.omm"))
        raws, errors = [], []
        for omm in omm_files:
            try:
                raws.append(type(self)(self.folder, subject_id=self.subject_id,
                                       session_id=omm.stem, selected_stem=omm.stem).load())
            except Exception as exc:
                errors.append({"session": omm.stem, "error": str(exc)})
        return raws, errors

    @staticmethod
    def _protocol_durations(metadata: dict[str, Any]) -> tuple[float, float, float]:
        match = re.search(r"(\d+)-(\d+)-(\d+)\.pro", metadata.get("timepath", ""), re.IGNORECASE)
        if not match:
            return 15.0, 30.0, 15.0
        return tuple(float(value) for value in match.groups())

    @staticmethod
    def _events(flags: np.ndarray, times: np.ndarray) -> list[dict[str, Any]]:
        code = flags[:, 0].astype(int)
        indices = np.flatnonzero(code != 0)
        return [{"sample": int(i), "time_s": float(times[i]), "code": int(code[i])} for i in indices]

    @staticmethod
    def _blocks(events: list[dict[str, Any]], sampling_rate: float,
                protocol: tuple[float, float, float] = (15.0, 30.0, 15.0)) -> list[Block]:
        blocks: list[Block] = []
        pre_start = 0
        onset = None
        offset = None
        for event in events:
            code, sample = event["code"], event["sample"]
            if code == 3 and not blocks:
                pre_start = sample
            elif code == 16:
                if onset is not None:
                    raise FNIRSImportError("BLOCK_INCOMPLETE", "检测到连续两个任务开始标记")
                onset = sample
            elif code == 32:
                if onset is None:
                    raise FNIRSImportError("BLOCK_INCOMPLETE", "任务结束标记之前缺少任务开始标记")
                offset = sample
            elif code == 1:
                if onset is None or offset is None:
                    raise FNIRSImportError("BLOCK_INCOMPLETE", "block 结束标记之前缺少完整任务标记")
                block = Block(len(blocks) + 1, pre_start, onset, offset, sample, sampling_rate)
                durations = block.as_dict()
                tolerance = 1.0 / sampling_rate + 1e-6
                ok = (abs(durations["pre_duration_s"] - protocol[0]) <= tolerance and
                      abs(durations["interview_duration_s"] - protocol[1]) <= tolerance and
                      abs(durations["post_duration_s"] - protocol[2]) <= tolerance)
                block.qc_status = "PASS" if ok else "WARN"
                blocks.append(block)
                pre_start, onset, offset = sample + 1, None, None
        if onset is not None or offset is not None:
            raise FNIRSImportError("BLOCK_INCOMPLETE", "记录末尾存在未闭合的任务 block")
        return blocks

    def _qc(self, files: dict[str, Path], times: np.ndarray, adc: np.ndarray, voltage: np.ndarray,
            absorbance: np.ndarray, hbo: np.ndarray, hbr: np.ndarray, blocks: list[Block],
            optical_valid: np.ndarray, warnings: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
        n_samples, n_channels, _ = adc.shape
        zero_ratio = np.mean(adc == 0, axis=(0, 2))
        saturation_ratio = np.mean(adc == 65535, axis=(0, 2))
        invalid_per_channel = 1.0 - optical_valid.mean(axis=(0, 2))
        samples_per_window = max(1, round(60 / np.median(np.diff(times))))
        cvs = []
        for ch in range(n_channels):
            windows = []
            signal = voltage[:, ch].mean(axis=1)
            for start in range(0, n_samples, samples_per_window):
                part = signal[start:start + samples_per_window]
                if len(part) > samples_per_window // 2 and np.mean(part):
                    windows.append(float(np.std(part) / np.mean(part)))
            cvs.append(float(np.median(windows)) if windows else float("nan"))
        usable = [(zero_ratio[i] == 0 and saturation_ratio[i] == 0 and
                   invalid_per_channel[i] <= 0.01 and np.isfinite(cvs[i]) and cvs[i] <= 0.075)
                  for i in range(n_channels)]
        valid_blocks = sum(block.qc_status == "PASS" for block in blocks)
        expected_blocks = int(metadata.get("loop", 0) or 0)
        if expected_blocks and len(blocks) != expected_blocks:
            warnings.append(f"检测到 {len(blocks)} 个 block，PAT 期望 {expected_blocks} 个")
        if len(blocks) < max(1, int((expected_blocks or 30) * 0.8)) or sum(usable) < n_channels // 2:
            overall = "FAIL"
        elif warnings or valid_blocks != len(blocks) or sum(usable) != n_channels:
            overall = "WARN"
        else:
            overall = "PASS"
        return {
            "status": overall,
            "profile": self.profile,
            "files": {key: {"name": path.name, "size": path.stat().st_size, "sha256": _sha256(path)}
                      for key, path in files.items()},
            "recording": {"n_samples": n_samples, "duration_s": float(times[-1]),
                          "sampling_interval_s": float(np.median(np.diff(times))),
                          "time_monotonic": bool(np.all(np.diff(times) > 0)),
                          "missing_samples": int(np.sum(np.abs(np.diff(times) - np.median(np.diff(times))) > 1e-6)),
                          "duplicated_timestamps": int(np.sum(np.diff(times) == 0))},
            "channels": {"detected": n_channels, "usable": int(sum(usable)),
                         "usable_indices": [i + 1 for i, ok in enumerate(usable) if ok],
                         "windowed_cv_per_channel": cvs,
                         "zero_ratio_per_channel": zero_ratio.tolist(),
                         "saturation_ratio_per_channel": saturation_ratio.tolist(),
                         "invalid_optical_ratio_per_channel": invalid_per_channel.tolist()},
            "optical": {"invalid_optical_samples": int((~optical_valid).sum()),
                        "invalid_optical_ratio": float((~optical_valid).mean()),
                        "hbo_nan_ratio": float(np.isnan(hbo).mean()), "hbr_nan_ratio": float(np.isnan(hbr).mean())},
            "task": {"detected_blocks": len(blocks), "valid_blocks": valid_blocks,
                     "expected_blocks": expected_blocks or None,
                     "timing_integrity": "PASS" if valid_blocks == len(blocks) else "WARN"},
            "warnings": warnings,
        }
