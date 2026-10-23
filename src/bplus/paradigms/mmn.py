"""Passive auditory oddball / MMN (sections 20-21).

Design rules encoded here (all parameters come from YAML, none are hard-coded):
  * standard and deviant are the SAME kind of event, so the analysis can compare them;
  * **至少 min_standards_between_deviants 个标准刺激夹在两个偏差之间**
    （LIT：Murphy 2022 原文 "each deviant tone had a minimum of four standard trials
     preceding it"；Pang 2014 亦为 "a minimum of three and a maximum of 11 standards"）；
  * 开头若干个试次强制为标准刺激，先建立"标准模板"；
  * the deviant ratio per block is data-driven, not a fixed "every 5th tone".
"""
from __future__ import annotations

import random

from ..triggers import TriggerCode
from .base import Event, Paradigm


class MMNParadigm(Paradigm):
    name = "mmn"

    def events(self) -> list[Event]:
        cfg = self.cfg
        n_blocks = int(cfg.get("n_blocks", 3))
        trials_per_block = int(cfg.get("trials_per_block", 240))
        p_dev = float(cfg.get("deviant_probability", 0.15))
        soa = float(cfg.get("soa_ms", 500.0)) / 1000.0
        tail = float(cfg.get("tail_s", 1.0))
        seed = int(cfg.get("random_seed", 20260922))
        rng = random.Random(seed)

        min_std = int(cfg.get("min_standards_between_deviants", 4))
        events: list[Event] = [Event(0.0, TriggerCode.MMN_START, "MMN_START")]
        t = float(cfg.get("start_delay_s", 5.0))
        trial_id = 0
        for block in range(1, n_blocks + 1):
            sequence = self._make_sequence(rng, trials_per_block, p_dev, min_std)
            for is_deviant in sequence:
                trial_id += 1
                if is_deviant:
                    events.append(Event(t, TriggerCode.MMN_DEVIANT, "MMN_DEVIANT", trial_id=trial_id,
                                        block_id=block, meta={"hz": cfg.get("deviant_hz", 1200)}))
                else:
                    events.append(Event(t, TriggerCode.MMN_STANDARD, "MMN_STANDARD", trial_id=trial_id,
                                        block_id=block, meta={"hz": cfg.get("standard_hz", 1000)}))
                t += soa
        events.append(Event(t + tail, TriggerCode.MMN_END, "MMN_END"))
        return self._sorted(events)

    @staticmethod
    def _make_sequence(rng: random.Random, n: int, p_dev: float, min_std: int = 4) -> list[bool]:
        """偏差概率 ~p_dev，且两个偏差之间至少 min_std 个标准刺激。

        实现要点（这是一个真实的工程约束，不是随手写的）：
          偏差间隔 S = 1/p_dev 个试次；其中必须包含 min_std 个强制标准 + 1 个偏差；
          剩下的 (S - 1 - min_std) 个位置用几何分布填充 → 抽到偏差的概率
              q = 1 / (S - 1 - min_std)
          若 S <= 1 + min_std（即 p_dev >= 1/(1+min_std)），则约束已经饱和，退化为
          "每 (1+min_std) 个试次一个偏差"的规则序列（此时无法同时保持随机性与该概率）。

        LIT 依据：
          * Murphy 2022（Braz J Psychiatry）：每个偏差前至少 4 个标准刺激（防适应）
          * Pang 2014（PLoS One）：偏差之间有 3–11 个标准刺激
          * 孙宏毅 2025（锚论文）：80/20 随机序列 + 1 Hz
        """
        seq: list[bool] = []
        spacing = 1.0 / p_dev if p_dev > 0 else float("inf")
        extra_slots = spacing - 1 - min_std
        q = 1.0 / extra_slots if extra_slots > 0 else 1.0
        since_last_deviant = 10 ** 6
        for _ in range(n):
            if len(seq) < min_std or since_last_deviant < min_std:
                seq.append(False)
                since_last_deviant += 1
                continue
            if rng.random() < q:
                seq.append(True)
                since_last_deviant = 0
            else:
                seq.append(False)
                since_last_deviant += 1
        return seq
