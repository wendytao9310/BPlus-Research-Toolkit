import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.reports import (assert_participant_clean, participant_soft_warnings,
                           render_participant_markdown, render_participant_pages,
                           render_researcher_markdown, to_html)
from bplus.state import StateEngine
from tests.test_state import FEATS


def _profile():
    return StateEngine().evaluate(FEATS, dq={"score": 88, "band": "GOOD", "band_zh": "好"},
                                  participant_id="T01", session_id="1").as_dict()


def test_participant_report_has_four_pages_and_no_raw_metrics():
    md = render_participant_markdown(_profile())
    assert_participant_clean(md)                     # 硬守卫：无单位/无原始指标
    pages = render_participant_pages(_profile())
    assert [p["page"] for p in pages] == [1, 2, 3, 4]
    assert all(p["rows"] for p in pages)


def test_participant_guard_catches_a_leak():
    with pytest.raises(AssertionError, match="泄露"):
        assert_participant_clean("你的 MMN 振幅是 3.2 μV")


def test_participant_guard_allows_the_required_disclaimer():
    assert participant_soft_warnings("以上判断不是诊断概率。") == ["概率"]


def test_researcher_report_contains_metrics_and_traceability():
    md = render_researcher_markdown(_profile(), FEATS)
    assert "RESEARCH ONLY" in md
    assert "nback.d_prime" in md and "eeg.mmn_amplitude_abs_uv" in md
    assert "CLINICAL" in md


def test_html_is_self_contained_and_hides_metrics_above_the_fold():
    html = to_html(_profile(), FEATS)
    assert html.startswith("<!doctype html>")
    assert "<style>" in html and "http://" not in html and "https://" not in html
    body_before_appendix = html.split("研究者附录")[0]
    assert "μV" not in body_before_appendix and "d_prime" not in body_before_appendix
