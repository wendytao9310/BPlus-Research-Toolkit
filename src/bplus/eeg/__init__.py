"""EEG import and software-validation helpers."""

from .simulation import read_curry_metadata, run_mmn_simulation
from .cgx import analyze_cgx_brainvision, analyze_cgx_bundle, write_cgx_outputs

__all__ = ["analyze_cgx_brainvision", "analyze_cgx_bundle", "read_curry_metadata", "run_mmn_simulation",
           "write_cgx_outputs"]
