# P0-4 Hardware Validation Plan

## Objective

Validate physical TTL trigger delivery and synchronization between:

- PsychoPy stimulus presentation
- Curry EEG system
- Shimadzu LABNIRS fNIRS system

The purpose is to verify that software-generated trigger events can be correctly delivered to acquisition hardware.

---

# Current Software Status

## Completed

- TriggerPulse abstraction implemented
- TTL pulse width control implemented
- Simulated trigger backend validated
- Trigger code mapping validated
- Synchronization self-test passed

Validation command:

```bash
PYTHONPATH=src python scripts/sync_check.py selftest
