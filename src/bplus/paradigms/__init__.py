from .base import Event, Paradigm
from .emotion import EmotionParadigm
from .mmn import MMNParadigm
from .nback import NBackParadigm
from .recovery import RecoveryParadigm
from .rest import RestParadigm
from .vft import VFTParadigm

REGISTRY = {
    "rest": RestParadigm,
    "mmn": MMNParadigm,
    "vft": VFTParadigm,
    "nback": NBackParadigm,
    "emotion": EmotionParadigm,
    "recovery": RecoveryParadigm,
}

__all__ = ["Event", "Paradigm", "REGISTRY", "RestParadigm", "MMNParadigm", "VFTParadigm",
           "NBackParadigm", "EmotionParadigm", "RecoveryParadigm"]


def build(name: str, cfg: dict) -> Paradigm:
    return REGISTRY[name](cfg)
