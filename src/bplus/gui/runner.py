"""会话运行器：试次表 -> 真实呈现（PsychoPy）或 DEMO 仿真，并产出行为日志。

真机：`run_session("nback", "P01", "1", out_dir, dummy=False)`
DEMO：`run_session("nback", "D01", "1", out_dir, dummy=True)`（无 PsychoPy 也能跑通）
"""
from __future__ import annotations

import csv
import random
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from .. import config as cfg_mod
from ..behavior import TrialResponse, evaluate_nback, summarize
from ..paradigms import REGISTRY
from ..realtime import NullWindow, SimulatedLine, TriggerPulse, run_events
from ..screens import Trial, build_trials
from ..timing import PulsePolicy
from ..triggers import TriggerManager
from .presenter import DummyPresenter, PsychoPyPresenter

BEHAVIOR_COLUMNS = ["participant_id", "session_id", "paradigm", "trial_index", "block_id", "condition",
                    "code", "onset_s", "stim", "is_target", "expected_key", "responded", "key",
                    "rt_ms", "correct", "valence", "arousal", "practice"]


class ExperimentAborted(RuntimeError):
    """Raised when the participant presses T to stop a paradigm safely."""


def _scale_visual_demo_trials(trials: list[Trial], scale: float = 0.35) -> list[Trial]:
    """Compress demo timing while keeping block instructions readable for 3 seconds."""
    scaled: list[Trial] = []
    accumulated_delay = 0.0
    for trial in sorted(trials, key=lambda item: item.onset_s):
        compressed_duration = max(1.0, trial.duration_s * scale)
        duration = max(3.0, compressed_duration) if trial.kind == "instruction" else compressed_duration
        scaled.append(replace(
            trial,
            onset_s=trial.onset_s * scale + accumulated_delay,
            duration_s=duration,
            response_window_s=(trial.response_window_s[0] * scale,
                               max(1.5, trial.response_window_s[1] * scale))
            if trial.response_window_s else None,
        ))
        if trial.kind == "instruction":
            accumulated_delay += duration - compressed_duration
    return scaled


@dataclass
class SessionRunResult:
    paradigm: str
    out_dir: Path
    trials: list[Trial]
    responses: list[TrialResponse]
    summary: dict
    trigger_log: Path | None = None
    behavior_log: Path | None = None
    notes: list[str] = field(default_factory=list)


def _dummy_response(trial: Trial, rng: random.Random) -> TrialResponse:
    """DEMO 模式：伪造"像人"的行为数据，用于跑通分析与报告链路（绝不用于科研结论）。"""
    r = TrialResponse(trial_id=trial.index, block_id=trial.block_id, condition=trial.condition,
                      is_target=trial.is_target, meta=dict(trial.meta))
    if trial.kind == "rating":
        r.valence, r.arousal = rng.randint(1, 5), rng.randint(1, 5)
        r.responded, r.key = True, f"valence={r.valence};arousal={r.arousal}"
        return r
    if trial.is_target is True:
        if rng.random() < 0.85:
            r.responded, r.key, r.rt_ms = True, trial.expected_key or "return", max(120.0, rng.gauss(480, 90))
    elif trial.is_target is False:
        if rng.random() < 0.08:
            r.responded, r.key, r.rt_ms = True, "space", max(120.0, rng.gauss(520, 110))
    return r


def run_session(paradigm: str, participant_id: str, session_id: str, out_dir: str | Path, *,
                dummy: bool = False, backend: str = "simulated", parallel_address: int = 0x0378,
                seed: int = 20260922, speed: float = 0.0, mode: str | None = None,
                pilot_staff: bool = False, visual_demo: bool = False) -> SessionRunResult:
    """运行一个范式会话。

    mode: DEMO | PILOT | REAL（默认由 dummy 推断）。
    **Emotion 范式在 REAL 模式下会被刺激库闸门拦下**，除非刺激库通过全部验证（§1/§47）；
    PILOT 模式（例如先用操作员本人做设备测试）可用 `pilot_staff=True` 放行，但会打印警告。
    """
    mode = mode or ("DEMO" if dummy else "REAL")
    visual_demo = visual_demo or mode == "VISUAL_DEMO"
    notes_mode: list[str] = []
    if paradigm == "emotion" and mode == "REAL":
        from ..stimuli import assert_real_mode_allowed
        assert_real_mode_allowed()          # 不通过则抛出指定错误信息
    if paradigm == "emotion" and mode == "PILOT":
        if not pilot_staff:
            raise RuntimeError(
                "Emotion in PILOT mode requires explicit confirmation:\n"
                "  Only the operator or a non-study participant may be used for equipment and workflow testing.\n"
                "  Re-run with --pilot-staff after confirmation; real participants require a validated stimulus library in REAL mode.")
        notes_mode.append("PILOT mode (operator): stimulus library not validated; data must not be used for research conclusions")
    cfg = cfg_mod.paradigm_config(paradigm)
    policy = PulsePolicy.from_config(cfg_mod.load_yaml("sync.yaml"))
    events = REGISTRY[paradigm](cfg).events()
    trials = build_trials(paradigm, cfg, events)
    if visual_demo:
        # Keep the real trial content while compressing the protocol timeline
        # while preserving each N-back rule/target page for three seconds.
        trials = _scale_visual_demo_trials(trials)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # 日志后端：真机时硬件边沿由 TriggerPulse 负责，这里只负责把事件写进日志
    from ..io import EventLog
    from ..triggers import LogOnlyBackend
    log = EventLog(out, participant_id=participant_id, session_id=session_id)
    manager = TriggerManager(participant_id, session_id, backends=[LogOnlyBackend()], log=log)

    notes: list[str] = list(notes_mode)
    if dummy and not visual_demo:
        window = NullWindow(speed=speed)
        presenter = DummyPresenter()
        line = SimulatedLine(clock=window.now)
        pulse = TriggerPulse(line=line, policy=policy, clock=window.now)
        notes.append("DEMO mode: no hardware or PsychoPy; behavioral data are simulated for workflow testing only")
    else:
        from ..realtime import ParallelLine, PsychoPyWindow
        window = PsychoPyWindow(size=(1280, 800), fullscreen=not visual_demo)
        presenter = PsychoPyPresenter()
        line = SimulatedLine() if visual_demo else ParallelLine(address=parallel_address)
        pulse = TriggerPulse(line=line, policy=policy)
        if visual_demo:
            notes.append("VISUAL_DEMO: PsychoPy display with simulated triggers; no acquisition hardware; data must not be used for research conclusions")

    presenter.prepare(window)
    rng = random.Random(seed)
    responses: list[TrialResponse] = []

    if not (dummy and not visual_demo):
        _show_instructions(paradigm, window, presenter)
        _show_countdown(window, presenter)
        window.reset_clock()

    def _fire(code: int, trial: Trial) -> None:
        """与 flip 同帧执行：既让硬件拉高，也写日志（保证两者时间一致）。"""
        pulse.arm(code)
        manager.send(code, trial_id=trial.index, block_id=trial.block_id, phase=paradigm)

    for trial in sorted(trials, key=lambda t: t.onset_s):
        _wait_until(trial.onset_s, window, interactive=not (dummy and not visual_demo))
        window.call_on_flip(_fire, trial.code, trial)
        if trial.kind == "tone":
            presenter.play_tone(trial)
            presenter.show(trial, window)
        elif trial.kind == "rating":
            presenter.draw_rating(trial, window)
        else:
            presenter.show(trial, window)
        window.flip()

        if dummy and not visual_demo:
            responses.append(_dummy_response(trial, rng))
        else:
            responses.append(_collect_response(trial, window, presenter))
            if trial.kind in {"image", "text"}:
                presenter.show_fixation(window)
                window.flip()
        pulse.poll()

    presenter.close()
    if hasattr(window, "win"):
        window.win.close()
    if dummy and not visual_demo:
        window.wait_until((trials[-1].onset_s if trials else 0) + policy.width_ms / 1000.0)
    pulse.poll()

    responses = evaluate_nback(responses, target_key=str(cfg.get("match_key", "return"))) if paradigm == "nback" else responses
    summary = summarize(responses) if paradigm == "nback" else {
        "n_trials": len(responses),
        "n_with_response": sum(1 for r in responses if r.responded),
    }

    behavior = out / f"sub-{participant_id}_ses-{session_id}_{paradigm}_behavior.csv"
    with behavior.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(BEHAVIOR_COLUMNS)
        for t, r in zip(sorted(trials, key=lambda x: x.onset_s), responses):
            w.writerow([participant_id, session_id, paradigm, t.index, t.block_id or "", t.condition,
                        t.code, f"{t.onset_s:.3f}", (t.text if t.kind != "image" else t.image or ""),
                        "" if t.is_target is None else int(t.is_target), t.expected_key or "",
                        int(r.responded), r.key or "", "" if r.rt_ms is None else f"{r.rt_ms:.1f}",
                        "" if r.correct is None else int(r.correct), r.valence or "", r.arousal or "",
                        int(bool(t.meta.get("practice")))])

    return SessionRunResult(paradigm=paradigm, out_dir=out, trials=trials, responses=responses,
                            summary=summary, trigger_log=log.csv_path, behavior_log=behavior, notes=notes)


def _collect_response(trial: Trial, window, presenter) -> TrialResponse:
    """真机：在反应窗口内轮询按键。"""
    from psychopy import core, event

    r = TrialResponse(trial_id=trial.index, block_id=trial.block_id, condition=trial.condition,
                      is_target=trial.is_target, meta=dict(trial.meta))
    if trial.kind == "rating":
        return _collect_emotion_rating(trial, window, presenter, r)
    if trial.response_window_s is None:
        # 无反应任务：按配置时长保持呈现。静息/恢复只有一个 trial，
        # 因此不能依赖“等待下一个 onset”来维持画面。
        deadline = core.Clock()
        while deadline.getTime() < max(0.0, trial.duration_s):
            if "t" in event.getKeys(keyList=["t"]):
                raise ExperimentAborted("The participant pressed T; the task was stopped safely")
            core.wait(0.01)
        return r
    lo, hi = trial.response_window_s
    clock = core.Clock()
    if lo > 0:
        core.wait(lo)
    keys = [trial.expected_key] if trial.expected_key else ["space", "return"]
    while clock.getTime() < hi:
        got = event.getKeys(keyList=[k for k in keys if k] + ["t"], timeStamped=clock)
        if got:
            if got[0][0] == "t":
                raise ExperimentAborted("The participant pressed T; the task was stopped safely")
            r.responded, r.key, r.rt_ms = True, got[0][0], float(got[0][1]) * 1000.0
            presenter.show_message(f"Response recorded: {r.key}", window, height=42)
            window.flip(); core.wait(0.25)
            break
        core.wait(0.002)
    return r


INSTRUCTIONS = {
    "rest": "Resting-state baseline\n\nKeep your eyes open, fixate on the central cross, remain quiet, and keep your body still.",
    "mmn": "Auditory MMN task\n\nFixate on the central cross and listen naturally to the sounds through the headphones. No response is required.",
    "vft": "Verbal Fluency Task\n\nSay as many words as possible beginning with each on-screen syllable. Do not repeat words or use personal or place names.",
    "nback": ("N-back working-memory task\n\n"
              "0-back: the target digit is shown first; press Enter when it appears.\n"
              "2-back: press Enter when the current digit matches the digit two trials earlier.\n"
              "Do not press otherwise; the rule is shown again before each block."),
    "emotion": "Emotion image task\n\nView the images; after each block, use numbers 1–5 to rate pleasantness and arousal separately.",
    "recovery": "Post-task recovery\n\nKeep your eyes open, fixate on the central cross, relax, and keep your body still.",
}


def _show_instructions(paradigm: str, window, presenter, seconds: float = 30.0) -> None:
    from psychopy import core, event
    clock = core.Clock()
    while clock.getTime() < seconds:
        remaining = max(0, int(seconds - clock.getTime()))
        presenter.show_message(f"{INSTRUCTIONS[paradigm]}\n\nPress S when you are ready\nPress T at any time to stop\n\nInstructions remaining: {remaining} s", window, height=36)
        window.flip()
        keys = event.getKeys(keyList=["s", "t"])
        if "t" in keys:
            raise ExperimentAborted("The participant pressed T during instructions; the task was stopped")
        if "s" in keys:
            return
        core.wait(0.02)


def _show_countdown(window, presenter) -> None:
    from psychopy import core, event
    for number in (3, 2, 1):
        presenter.show_message(f"The task is about to begin\n\n{number}", window, height=96)
        window.flip()
        clock = core.Clock()
        while clock.getTime() < 1.0:
            if "t" in event.getKeys(keyList=["t"]):
                raise ExperimentAborted("The participant pressed T during the countdown; the task was stopped")
            core.wait(0.01)


def _wait_until(target: float, window, *, interactive: bool) -> None:
    if not interactive:
        window.wait_until(target)
        return
    from psychopy import event
    while window._clock.getTime() < target:
        if "t" in event.getKeys(keyList=["t"]):
            raise ExperimentAborted("The participant pressed T; the task was stopped safely")
        window.flip()


def _collect_emotion_rating(trial: Trial, window, presenter, response: TrialResponse) -> TrialResponse:
    from psychopy import core, event
    clock = core.Clock()
    values = []
    prompts = [("Pleasantness", "1=very unpleasant    5=very pleasant"),
               ("Arousal", "1=very calm    5=very aroused")]
    for label, scale in prompts:
        while True:
            chosen = values[-1] if values else None
            prior = f"\nPleasantness selected: {chosen}" if label == "Arousal" else ""
            presenter.show_message(f"{label}\n\n{scale}\n\nPress a number from 1 to 5{prior}\nPress T to stop", window, height=42)
            window.flip()
            keys = event.getKeys(keyList=["1", "2", "3", "4", "5", "num_1", "num_2", "num_3", "num_4", "num_5", "t"])
            if "t" in keys:
                raise ExperimentAborted("The participant pressed T during rating; the task was stopped safely")
            numeric = next((k[-1] for k in keys if k[-1:] in "12345"), None)
            if numeric:
                values.append(int(numeric))
                presenter.show_message(f"{label} recorded: {numeric}", window, height=54)
                window.flip(); core.wait(0.6)
                break
            core.wait(0.01)
    response.valence, response.arousal = values
    response.responded = True
    response.key = f"valence={values[0]};arousal={values[1]}"
    response.rt_ms = clock.getTime() * 1000.0
    presenter.show_message(f"Block rating complete\n\nPleasantness: {values[0]}\nArousal: {values[1]}", window, height=48)
    window.flip(); core.wait(1.0)
    return response
