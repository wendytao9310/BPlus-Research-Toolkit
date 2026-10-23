# P0-3 Trigger Pipeline Validation

Date:
2026-09-23

## Software validation

### Unit test

Command:

pytest -q

Result:

PASS

### Trigger self test

Command:

PYTHONPATH=src python scripts/sync_check.py selftest

Result:

PASS

Offset:
38.393 ms

Jitter SD:
6.121 ms

Missing pulse detection:
PASS

### Simulated TTL

Command:

PYTHONPATH=src python scripts/sync_check.py emit --backend simulated

Result:

PASS

Codes:

101-110

## Status

Software trigger pipeline validated.
Ready for physical hardware validation.
