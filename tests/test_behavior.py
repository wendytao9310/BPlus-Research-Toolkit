import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.behavior import TrialResponse, d_prime, evaluate_nback, rt_variability, summarize


def _trial(tid, is_target, responded=False, key=None, rt=None):
    return TrialResponse(trial_id=tid, is_target=is_target, responded=responded, key=key, rt_ms=rt)


def test_nback_scoring_counts_every_outcome():
    rows = [
        _trial(1, True, True, "return", 500),      # hit（按匹配键）
        _trial(2, True, False),                    # omission
        _trial(3, False, True, "return", 600),     # false alarm（非目标却按匹配键）
        _trial(4, False, False),                   # correct rejection（不按）
        _trial(5, False, True, "space", 450),      # 按非匹配键 → 也算正确拒绝
    ]
    evaluate_nback(rows)
    s = summarize(rows)
    assert (s["hits"], s["omissions"], s["false_alarms"], s["correct_rejections"]) == (1, 1, 1, 2)
    assert s["n_targets"] == 2 and s["n_nontargets"] == 3
    assert 0.0 <= s["accuracy"] <= 1.0
    assert s["accuracy"] == 0.6                    # 5 个试次里 3 个正确
    assert s["n_rt"] == 2                          # hit(500) + 非匹配键(450) 都算正确反应时


def test_d_prime_behaves_monotonically():
    perfect = d_prime(20, 20, 0, 80)
    good = d_prime(16, 20, 4, 80)
    chance = d_prime(10, 20, 40, 80)
    assert perfect > good > chance
    assert chance < 1.0            # 接近随机时 d' 接近 0-1
    assert perfect < 6.0           # log-linear 校正避免无穷大


def test_rt_variability_is_cv():
    assert abs(rt_variability([500, 500, 500, 500]) - 0.0) < 1e-9
    cv = rt_variability([400, 500, 600])
    assert 0.15 < cv < 0.25


def test_only_the_match_key_counts_as_a_target_response():
    rows = evaluate_nback([_trial(1, True, True, "return", 450),
                           _trial(2, False, True, "return", 450),
                           _trial(3, False, True, "space", 450)])
    assert rows[0].correct is True                 # 目标 + 匹配键
    assert rows[1].correct is False                # 非目标 + 匹配键 = 虚报
    assert rows[2].correct is True                 # 非目标 + 非匹配键 = 正确拒绝
    assert [r.pressed_target_key for r in rows] == [True, True, False]
