import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod
from bplus.gui.runner import _scale_visual_demo_trials
from bplus.screens import build_trials

NAMES = ("rest", "mmn", "vft", "nback", "emotion", "recovery")


def test_every_paradigm_builds_a_trial_table():
    for name in NAMES:
        trials = build_trials(name)
        assert trials, name
        assert all(t.duration_s >= 0 for t in trials)
        onsets = [t.onset_s for t in trials]
        assert onsets == sorted(onsets), name


def test_mmn_is_passive_and_has_tones():
    trials = build_trials("mmn")
    assert all(t.kind == "tone" for t in trials)
    assert all(t.is_target is None and t.expected_key is None for t in trials)
    hz = {t.tone_hz for t in trials}
    assert hz == {1000.0, 2000.0}          # LIT: 锚论文 1000 Hz vs 2000 Hz


def test_nback_trials_carry_digits_and_response_windows():
    trials = build_trials("nback")
    cues = [t for t in trials if t.kind == "instruction"]
    digits = [t for t in trials if t.kind == "text"]
    assert len(cues) == 7 and len(digits) == 104
    assert all(t.duration_s == 3.0 and t.response_window_s is None for t in cues)
    assert all("Enter" in t.text and "do not press" in t.text.lower() for t in cues)
    assert all("target digit" in t.text.lower() for t in cues if t.condition == "0-back-cue")
    assert all("two trials earlier" in t.text.lower() for t in cues if t.condition == "2-back-cue")
    targets = [t for t in digits if t.is_target]
    assert targets and all(t.expected_key == "return" for t in targets)
    assert all(t.response_window_s == (0.0, 2.0) for t in digits)   # LIT: 2 s 周期
    assert all(t.text.isdigit() for t in digits)


def test_nback_visual_demo_keeps_target_cues_visible_for_three_seconds():
    trials = _scale_visual_demo_trials(build_trials("nback"))
    cues = [t for t in trials if t.kind == "instruction"]
    assert len(cues) == 7
    assert all(t.duration_s == 3.0 for t in cues)
    for cue in cues:
        first_digit = next(t for t in trials if t.block_id == cue.block_id and t.kind == "text")
        assert first_digit.onset_s >= cue.onset_s + 3.0


def test_emotion_trials_have_images_and_block_ratings():
    trials = build_trials("emotion")
    images = [t for t in trials if t.kind == "image"]
    ratings = [t for t in trials if t.kind == "rating"]
    assert len(images) == 24 and len(ratings) == 6
    assert all(t.image.startswith("stimuli/emotion/") for t in images)
    assert all("pleasantness" in t.text.lower() for t in ratings)


def test_vft_trials_follow_the_lit_single_cycle():
    trials = build_trials("vft")
    assert [t.condition for t in trials] == ["pre_rest", "task", "task", "task", "task", "post_rest"]
    assert trials[0].duration_s == 30 and trials[-1].duration_s == 60
    assert all(t.duration_s == 15 for t in trials[1:5])
