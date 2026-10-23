import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod
from bplus.paradigms import REGISTRY
from bplus.triggers import TriggerCode

NAMES = ("rest", "mmn", "vft", "nback", "emotion", "recovery")


@pytest.mark.parametrize("name", NAMES)
def test_every_paradigm_declares_evidence(name):
    cfg = cfg_mod.paradigm_config(name)
    assert "evidence" in cfg, f"{name} must carry an evidence block (section 6-8)"
    assert cfg["evidence"].get("status"), name


@pytest.mark.parametrize("name", NAMES)
def test_events_are_sorted_positive_and_typed(name):
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    events = REGISTRY[name](paradigms[name]).events()
    assert events
    assert all(e.onset >= 0 for e in events)
    assert all(isinstance(e.code, TriggerCode) for e in events)
    onsets = [e.onset for e in events]
    assert onsets == sorted(onsets)


def test_mmn_deviant_ratio_and_no_adjacent_deviants():
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    events = REGISTRY["mmn"](paradigms["mmn"]).events()
    trials = [e for e in events if e.code in (TriggerCode.MMN_STANDARD, TriggerCode.MMN_DEVIANT)]
    assert len(trials) == 2 * 170
    deviant_ratio = sum(e.code is TriggerCode.MMN_DEVIANT for e in trials) / len(trials)
    assert 0.12 <= deviant_ratio <= 0.18   # 目标 15%（LIT 折中），允许 ±3pp
    kinds = "".join("D" if e.code is TriggerCode.MMN_DEVIANT else "S" for e in trials)
    assert "DD" not in kinds
    # LIT 规则：偏差之间至少 4 个标准刺激（Murphy 2022）
    import re as _re
    for m in _re.finditer(r"D(S*)D", kinds):
        assert len(m.group(1)) >= 4, f"两个偏差之间只有 {len(m.group(1))} 个标准刺激"


def test_nback_block_structure_and_target_rate():
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    events = REGISTRY["nback"](paradigms["nback"]).events()

    blocks = [e for e in events if e.code in (TriggerCode.NBACK_0BACK, TriggerCode.NBACK_2BACK)]
    main = [e for e in blocks if not e.meta.get("practice")]
    practice = [e for e in blocks if e.meta.get("practice")]
    assert len(main) == 6 and Counter(int(e.code) for e in main) == {301: 3, 302: 3}
    assert len(practice) == 1

    order = [e.meta["level"] for e in main]
    assert all(not (order[i] == order[i - 1] == order[i - 2]) for i in range(2, len(order)))

    for block in main:
        trials = [e for e in events if e.block_id == block.block_id
                  and e.code in (TriggerCode.NBACK_TARGET, TriggerCode.NBACK_NONTARGET)]
        assert len(trials) == 16
        targets = sum(e.code is TriggerCode.NBACK_TARGET for e in trials)
        assert 4 <= targets <= 5
        if block.meta["level"] == 0:
            target_digit = block.meta["target_digit"]
            assert target_digit is not None
            assert all((e.meta["digit"] == target_digit) == e.meta["is_target"] for e in trials)
        else:
            assert block.meta["target_digit"] is None
            assert all((e.meta["digit"] == trials[i - 2].meta["digit"]) == e.meta["is_target"]
                       for i, e in enumerate(trials) if i >= 2)


def test_vft_is_a_single_lit_cycle():
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    cfg = paradigms["vft"]
    events = REGISTRY["vft"](cfg).events()
    names = [e.name for e in events]
    assert names.count("VFT_BLOCK") == cfg["sub_blocks"] == 4
    assert names.count("VFT_REST_PRE") == 1 and names.count("VFT_REST_POST") == 1
    pre = next(e for e in events if e.name == "VFT_REST_PRE")
    post = next(e for e in events if e.name == "VFT_REST_POST")
    assert pre.meta["duration_s"] == 30 and post.meta["duration_s"] == 60


def test_emotion_ratings_collect_valence_and_arousal_separately():
    paradigms = {n: cfg_mod.paradigm_config(n) for n in NAMES}
    events = REGISTRY["emotion"](paradigms["emotion"]).events()
    ratings = [e for e in events if e.code is TriggerCode.EMOTION_RATING]
    blocks = [e for e in events if e.code is TriggerCode.EMOTION_BLOCK]
    assert len(blocks) == 6 and len(ratings) == 6          # 块末集中评分（LIT: block design）
    assert all(e.meta["scales"] == ["valence", "arousal"] for e in ratings)
    face_codes = [int(e.code) for e in events if int(e.code) in (401, 402, 403)]
    assert Counter(face_codes) == {401: 8, 402: 8, 403: 8}
