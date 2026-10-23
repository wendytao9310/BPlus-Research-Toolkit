import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config
from bplus.paradigms.emotion import EmotionParadigm
from bplus.triggers import TriggerCode


def test_emotion_events_carry_visual_measurement_windows():
    cfg = config.paradigm_config("emotion")
    events = EmotionParadigm(cfg).events()
    stimuli = [event for event in events if event.code in {
        TriggerCode.EMOTION_NEUTRAL,
        TriggerCode.EMOTION_POSITIVE,
        TriggerCode.EMOTION_NEGATIVE,
    }]
    assert len(stimuli) == 24
    assert all(event.meta["visual_measurement_anchor"] is True for event in stimuli)
    assert all(event.meta["response_windows_s"]["early_response"] == [0.5, 2.0] for event in stimuli)
