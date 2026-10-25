# BPlus Research Toolkit

An English research-software edition of the BPlus multimodal experiment platform for adolescent mental-health research. It preserves the task logic, timing, stimuli, event markers, response capture, multimodal import workflow, quality control, and report generation used by the working BPlus project.

> **Research-use preview.** BPlus is not a medical device, does not diagnose depression, and must not be used to predict or manage suicide risk. Any clinical interpretation requires qualified professionals, an approved protocol, validated instruments, and local ethics approval.

## What it includes

- Five participant-facing paradigms: resting state, auditory MMN, verbal fluency (VFT), N-back, and emotion processing.
- Visible response confirmation, task instructions, countdowns, stop controls, and trial-level behavioral export.
- Session-level event markers designed for EEG and fNIRS alignment.
- Batch import and unified analysis for EEG, fNIRS, behavioral, eye-tracking, physiology, and clinician-entered measures.
- Quality-control summaries, research metrics, participant-facing status pages, and a researcher appendix.
- DEMO, VISUAL_DEMO, and gated REAL modes sharing the same protocol definitions.

## Research workflow

```text
Participant/session registration
        -> paradigm acquisition + event markers
        -> modality-specific import staging
        -> identity and session matching
        -> preprocessing and quality control
        -> unified feature table
        -> one consolidated report
```

Modalities are staged first and analysed together only after the operator selects the unified-analysis action. Matching is based on participant and session identifiers; a filename match alone is not treated as scientific proof that recordings belong to the same session.

## Quick start on macOS

Requirements: macOS, Python 3.11, and approximately 20 GiB free disk space for a full PsychoPy environment.

```bash
git clone https://github.com/wendytao9310/BPlus-Research-Toolkit.git
cd BPlus-Research-Toolkit
bash scripts/setup_environment.sh
```

Then double-click **BPlus English.command**. The launcher writes local outputs under `data/`, which is excluded from version control.

For a lightweight code test without acquisition hardware:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_demo.py --participant DEMO01
```

## Current validation boundary

- The English interface is a language-localized clone of the working BPlus task implementation; task parameters and event structure are unchanged.
- Software-only DEMO and report-generation paths have been exercised locally.
- Hardware timing, device triggers, electrode/optode placement, and acquisition quality must be validated at each laboratory site before participant use.
- Included emotion images are for demonstration/pilot workflow only. They are not a clinically validated adolescent stimulus set.
- Generated state labels are research summaries derived from configured inputs. They are not diagnoses or individualized treatment recommendations.

## Data and privacy

No participant data are included in this repository. Do not commit raw EEG, fNIRS, video, eye-tracking, physiological, clinical, or behavioral records. Use coded participant identifiers, keep the re-identification key outside the repository, and follow institutional retention and access rules. See [PRIVACY.md](PRIVACY.md).

## Distribution

Download the verified source package from the [latest GitHub Release](https://github.com/wendytao9310/BPlus-Research-Toolkit/releases/latest). A portable macOS application requires a bundled Python/PsychoPy runtime. For normal double-click installation without Gatekeeper warnings, the application must additionally be signed with an Apple Developer ID and notarized.

## Project status

Version: **0.1.2 public research preview**

Original BPlus source code is released under the [Apache License 2.0](LICENSE). Documentation and third-party stimulus assets retain their stated terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

If you use or evaluate this research software, cite the release metadata in [CITATION.cff](CITATION.cff). A DOI can be added after archival publication.

