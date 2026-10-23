"""呈现器：真机用 PsychoPy 绘制，无头模式只记录"画了什么"。"""
from __future__ import annotations

import math
import struct
import tempfile
import wave
from pathlib import Path


def make_tone_wav(hz: float, ms: float, path: str | Path, *, rate: int = 44100, amp: float = 0.35) -> Path:
    """用标准库生成纯音 wav（5 ms 升降沿），避免额外依赖 numpy/audacity。"""
    path = Path(path)
    n = int(rate * ms / 1000.0)
    ramp = max(1, int(rate * 0.005))
    frames = bytearray()
    for i in range(n):
        env = 1.0
        if i < ramp:
            env = i / ramp
        elif i > n - ramp:
            env = max(0.0, (n - i) / ramp)
        frames += struct.pack("<h", int(32767 * amp * env * math.sin(2 * math.pi * hz * i / rate)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


class DummyPresenter:
    """无头：记录每个试次画了什么（供测试与 DEMO 日志）。"""

    def __init__(self) -> None:
        self.drawn: list[str] = []

    def prepare(self, window) -> None:
        return None

    def show(self, trial, window) -> None:
        self.drawn.append(trial.text if trial.kind != "image" else f"IMG:{trial.image}")

    def play_tone(self, trial) -> None:
        self.drawn.append(f"TONE:{trial.tone_hz:.0f}Hz/{trial.tone_ms:.0f}ms")

    def draw_rating(self, trial, window) -> None:
        self.drawn.append("RATING")

    def close(self) -> None:
        return None


class PsychoPyPresenter:
    """真机：PsychoPy TextStim / ImageStim / Sound。"""

    def __init__(self, *, text_height: int = 64, font: str = "Hiragino Sans GB") -> None:
        self._text_height = text_height
        self._font = font
        self._visual = None
        self._sound = None
        self._text_stim = None
        self._image_stim = None
        self._sound_stim = None
        self._tone_cache: dict[tuple[float, float], Path] = {}

    def prepare(self, window) -> None:
        # PTB currently fails on some Apple Silicon installations when its
        # PsychHID extension cannot resolve libusb. SoundDevice is an installed
        # CoreAudio-backed alternative and is sufficient for software demos.
        from psychopy import prefs
        prefs.hardware["audioLib"] = ["sounddevice"]
        from psychopy import sound, visual

        self._visual, self._sound = visual, sound
        self._text_stim = visual.TextStim(window.win, text="+", color="white", font=self._font,
                                          height=self._text_height, wrapWidth=1100)
        self._image_stim = visual.ImageStim(window.win, image=None, size=(600, 600))
        self._sound_stim = sound.Sound

    def show(self, trial, window) -> None:
        if trial.kind == "image":
            self._image_stim.image = trial.image
            self._image_stim.draw()
        else:
            self._text_stim.text = trial.text
            self._text_stim.draw()

    def draw_rating(self, trial, window) -> None:
        self._text_stim.text = trial.text
        self._text_stim.draw()

    def show_fixation(self, window) -> None:
        self._text_stim.text = "+"
        self._text_stim.draw()

    def show_message(self, text: str, window, *, height: int | None = None) -> None:
        self._text_stim.text = text
        self._text_stim.height = height or self._text_height
        self._text_stim.draw()
        self._text_stim.height = self._text_height

    def play_tone(self, trial) -> None:
        key = (float(trial.tone_hz or 0), float(trial.tone_ms or 0))
        if key not in self._tone_cache:
            bundled = Path("stimuli/audio/mmn") / f"tone_{int(key[0])}Hz_{int(key[1])}ms.wav"
            tmp = bundled if bundled.exists() else Path(tempfile.gettempdir()) / f"bplus_tone_{int(key[0])}_{int(key[1])}.wav"
            self._tone_cache[key] = tmp if tmp.exists() else make_tone_wav(key[0], key[1], tmp)
        self._sound_stim(str(self._tone_cache[key])).play()

    def close(self) -> None:
        return None
