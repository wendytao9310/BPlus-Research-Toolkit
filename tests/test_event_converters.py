import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scripts.convert_curry_events import main as curry_main, parse_csv, parse_txt
from scripts.convert_lightnirs_marks import extract, guess_mode, main as lightnirs_main


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_curry_event_list_csv_is_parsed_and_written(tmp_path):
    src = _write(tmp_path / "curry_events.csv",
                 "Type,Time(s)\n"
                 "standard,10.000\n"
                 "deviant,10.500\n"
                 "0,10.600\n"                       # 0 = 无事件，应跳过
                 "standard,11.000\n")
    pairs = parse_csv(src, code_map={"standard": 101, "deviant": 102}, time_unit="auto")
    assert [c for c, _ in pairs] == [101, 102, 101]
    out = tmp_path / "out.csv"
    assert curry_main(["--csv", str(src), "--code-map", "standard=101,deviant=102",
                       "--out", str(out)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 3 and rows[0]["code"] == "101" and float(rows[0]["t"]) == 10.0


def test_curry_millisecond_autodetect():
    """最大值 > 1000 → 判定为毫秒并自动换算。"""
    pairs = parse_csv(_write(Path("/tmp/_c.csv"), "code,time\n101,12000\n102,12500\n"),
                      code_map={}, time_unit="auto")
    assert pairs[0] == (101, 12.0) and pairs[1] == (102, 12.5)


def test_curry_free_text_parsing():
    txt = _write(Path("/tmp/_c.txt"), "Code: 101  Time: 12.345 s\nCode: 102 Time: 13.000\n")
    pairs = parse_txt(txt, code_map={}, time_unit="auto")
    assert pairs == [(101, 12.345), (102, 13.0)]


def test_lightnirs_event_mode_and_diagnostics(tmp_path):
    src = _write(tmp_path / "fnirs.csv",
                 "Time(s),CH1 Oxy-Hb,Mark\n"
                 "0.000,0.1,\n0.075,0.2,\n0.150,0.3,101\n0.225,0.2,\n0.300,0.1,102\n")
    out = tmp_path / "marks.csv"
    assert lightnirs_main(["--csv", str(src), "--time-col", "Time(s)", "--marker-col", "Mark",
                           "--out", str(out)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["code"] for r in rows] == ["101", "102"]


def test_lightnirs_change_mode_detects_edges():
    rows = [{"t": str(i * 0.075), "m": "0" if i < 3 else ("101" if i < 6 else "102")}
            for i in range(9)]
    mode = guess_mode(rows, "m")
    assert mode == "change"
    pairs = extract(rows, "t", "m", mode)
    assert [c for c, _ in pairs] == [101, 102]


def test_lightnirs_missing_column_fails_loudly(tmp_path):
    src = _write(tmp_path / "fnirs.csv", "Time(s),Oxy\n0,1\n")
    with pytest.raises(SystemExit, match="不在文件里"):
        lightnirs_main(["--csv", str(src), "--time-col", "Time(s)", "--marker-col", "Mark",
                        "--out", str(tmp_path / "x.csv")])
