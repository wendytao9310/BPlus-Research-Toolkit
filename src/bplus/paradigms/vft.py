"""Chinese phonemic verbal fluency task (VFT) — single cycle, LIT design.

证据（见 configs/paradigms/vft.yaml）：孙宏毅 等, 生物医学工程学杂志 2025;42(4):701-706,
DOI:10.7507/1001-5515.202503053 —— 30 s 预任务休息（连续计数）+ 60 s 任务（4 个 15 s 子模块，
每模块 4 个中文音节）+ 60 s 任务后休息（连续计数）。
"""
from __future__ import annotations

from ..triggers import TriggerCode
from .base import Event, Paradigm


class VFTParadigm(Paradigm):
    name = "vft"

    def events(self) -> list[Event]:
        cfg = self.cfg
        rest_before = float(cfg.get("block_rest_before_s", 30.0))
        task_s = float(cfg.get("block_task_s", 60.0))
        rest_after = float(cfg.get("block_rest_after_s", 60.0))
        prompt_s = float(cfg.get("prompt_s", 5.0))
        n_sub = int(cfg.get("sub_blocks", 4))
        syllables = list(cfg.get("prompts", []))

        events = [Event(0.0, TriggerCode.VFT_START, "VFT_START")]
        t = float(cfg.get("start_delay_s", 0.0)) + prompt_s

        # 1) 预任务休息（连续计数）
        events.append(Event(t, TriggerCode.VFT_REST, "VFT_REST_PRE", block_id=0,
                            meta={"kind": "pre_rest", "counting": True, "duration_s": rest_before}))
        t += rest_before

        # 2) 任务期：n_sub 个等长子模块，每个子模块入口打一个 block 码
        sub_len = task_s / n_sub
        for i in range(n_sub):
            syllable = syllables[i] if i < len(syllables) else {}
            events.append(Event(t, TriggerCode.VFT_BLOCK, "VFT_BLOCK", block_id=i + 1,
                                meta={"kind": "task", "sub_block": i + 1, "sub_block_s": sub_len,
                                      "prompt": syllable.get("text", ""), "prompt_kind": syllable.get("kind", "phonemic")}))
            t += sub_len

        # 3) 任务后休息（连续计数）
        events.append(Event(t, TriggerCode.VFT_REST, "VFT_REST_POST", block_id=n_sub + 1,
                            meta={"kind": "post_rest", "counting": True, "duration_s": rest_after}))
        t += rest_after

        events.append(Event(t + float(cfg.get("tail_s", 5.0)), TriggerCode.VFT_END, "VFT_END"))
        return self._sorted(events)
