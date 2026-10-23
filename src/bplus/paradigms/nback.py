"""0-back / 2-back working-memory task (sections 23-25).

Timing architecture and block structure follow the MIT-licensed fNIRS implementation
(Khadijakhanbme/N-back-Cognitive-Load-Task), which itself follows the Oxford N-back timing
conventions. The number of blocks here is reduced by PROJECT_DEFAULT so the task fits the
20-minute computer-paradigm budget; the reduction is flagged in `evidence:`.
"""
from __future__ import annotations

import random

from ..triggers import TriggerCode
from .base import Event, Paradigm


class NBackParadigm(Paradigm):
    name = "nback"

    def events(self) -> list[Event]:
        cfg = self.cfg
        digits = list(cfg.get("digits", list(range(10))))
        stim_s = float(cfg.get("stimulus_s", 0.5))
        isi_s = float(cfg.get("isi_s", 1.0))
        cue_s = float(cfg.get("cue_s", 3.0))
        rest_s = float(cfg.get("rest_s", 20.0))
        n_trials = int(cfg.get("trials_per_block", 16))
        n_per_cond = int(cfg.get("n_blocks_per_condition", 3))
        tmin = int(cfg.get("targets_min", 4))
        tmax = int(cfg.get("targets_max", 5))
        practice_blocks = int(cfg.get("practice_blocks", 1))
        rng = random.Random(int(cfg.get("random_seed", 20260922)))

        order = self._block_order(n_per_cond, rng)
        events: list[Event] = [Event(0.0, TriggerCode.NBACK_START, "NBACK_START")]
        t = float(cfg.get("start_delay_s", 5.0))

        # practice (never analysed)
        for p in range(1, practice_blocks + 1):
            t = self._block(events, t, level=0, trials=8, cue_s=cue_s, stim_s=stim_s,
                            isi_s=isi_s, rest_s=rest_s, rng=rng, digits=digits,
                            block_id=100 + p, practice=True, targets=(2, 3))

        for block_id, level in enumerate(order, start=1):
            t = self._block(events, t, level=level, trials=n_trials, cue_s=cue_s, stim_s=stim_s,
                            isi_s=isi_s, rest_s=rest_s, rng=rng, digits=digits,
                            block_id=block_id, practice=False, targets=(tmin, tmax))

        events.append(Event(t + float(cfg.get("tail_s", 5.0)), TriggerCode.NBACK_END, "NBACK_END"))
        return self._sorted(events)

    # -- helpers ----------------------------------------------------------------------
    @staticmethod
    def _block_order(n_per_cond: int, rng: random.Random) -> list[int]:
        order = [0] * n_per_cond + [2] * n_per_cond
        for _ in range(200):  # rejection sampling: no more than 2 identical in a row
            rng.shuffle(order)
            if all(not (order[i] == order[i - 1] == order[i - 2]) for i in range(2, len(order))):
                return order
        return order

    def _block(self, events, t, *, level, trials, cue_s, stim_s, isi_s, rest_s, rng,
               digits, block_id, practice, targets):
        code = TriggerCode.NBACK_0BACK if level == 0 else TriggerCode.NBACK_2BACK
        seq, target_idx, target_digit = self._make_stream(rng, digits, trials, level, targets)
        events.append(Event(t, code, code.name, block_id=block_id,
                            meta={"level": level, "practice": practice,
                                  "target_digit": target_digit, "duration_s": cue_s}))
        t += cue_s

        for i, digit in enumerate(seq):
            trial_id = block_id * 1000 + i + 1
            is_target = i in target_idx
            code = TriggerCode.NBACK_TARGET if is_target else TriggerCode.NBACK_NONTARGET
            events.append(Event(t, code, code.name, trial_id=trial_id, block_id=block_id,
                                meta={"level": level, "digit": digit, "is_target": is_target,
                                      "practice": practice, "target_digit": target_digit}))
            t += stim_s + isi_s
        t += rest_s
        return t

    @staticmethod
    def _make_stream(rng, digits, trials, level, targets):
        targets_min, targets_max = targets
        n_targets = rng.randint(targets_min, targets_max)
        n_targets = min(n_targets, trials - 1)
        idx = set(rng.sample(range(level, trials), n_targets)) if trials > level else set()

        if level == 0:
            target_digit = rng.choice(digits)
            non_targets = [digit for digit in digits if digit != target_digit]
            if not non_targets:
                raise ValueError("0-back requires at least two distinct digits")
            seq = [target_digit if i in idx else rng.choice(non_targets) for i in range(trials)]
            return seq, idx, target_digit

        seq = [rng.choice(digits) for _ in range(trials)]
        if level == 2:
            for i in range(2, trials):          # make 2-back repeats impossible to detect by chance
                if seq[i] == seq[i - 2]:
                    seq[i] = (seq[i] + rng.randint(1, 9)) % 10
        for i in sorted(idx):
            seq[i] = seq[i - level]
        return seq, idx, None
