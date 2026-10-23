from bplus.trigger_mapping import PhysicalTriggerMap, DEFAULT_MAP_PATH
from bplus.triggers import TriggerCode


def test_physical_mapping_covers_all_trigger_codes():
    mapping = PhysicalTriggerMap.from_yaml()

    logical_codes = {int(code) for code in TriggerCode}

    assert set(mapping.logical_to_physical) == logical_codes


def test_physical_mapping_is_unique_and_in_range():
    mapping = PhysicalTriggerMap.from_yaml()

    physical_codes = list(mapping.logical_to_physical.values())

    assert len(physical_codes) == len(set(physical_codes))
    assert mapping.low_code not in physical_codes

    assert all(
        mapping.physical_code_min <= code <= mapping.physical_code_max
        for code in physical_codes
    )


def test_nback_target_mapping():
    mapping = PhysicalTriggerMap.from_yaml()

    assert mapping.to_physical(303) == 21
    assert mapping.to_logical(21) == 303


def test_recovery_end_mapping():
    mapping = PhysicalTriggerMap.from_yaml()

    assert mapping.to_physical(601) == 37
    assert mapping.to_logical(37) == 601


def test_unknown_logical_code_fails():
    mapping = PhysicalTriggerMap.from_yaml()

    try:
        mapping.to_physical(9999)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown logical code must fail")


def test_unknown_physical_code_fails():
    mapping = PhysicalTriggerMap.from_yaml()

    try:
        mapping.to_logical(255)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown physical code must fail")


def test_trigger_pulse_maps_logical_303_to_physical_21_and_holds_100ms():
    """Logical code stays 303 while the physical TTL line emits code 21."""
    from bplus.realtime import SimulatedLine, TriggerPulse
    from bplus.timing import PulsePolicy

    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            return self.now

    mapper = PhysicalTriggerMap.from_yaml(DEFAULT_MAP_PATH)
    clock = FakeClock()
    line = SimulatedLine(clock=clock)
    policy = PulsePolicy(width_ms=100, min_gap_ms=500)

    pulse = TriggerPulse(
        line=line,
        policy=policy,
        clock=clock,
        mapper=mapper,
    )

    # NBACK_TARGET: logical 303 -> physical TTL 21
    pulse.arm(303)

    assert pulse.events == [(0.0, 303)]
    assert pulse.physical_events == [(0.0, 21)]
    assert line.codes == [21]
    assert line.edges == [(0.0, "high", 21)]

    # At 99 ms the TTL pulse must still be HIGH.
    clock.now = 0.099
    assert pulse.poll() is False
    assert line.edges == [(0.0, "high", 21)]

    # At 100 ms the TTL pulse must return LOW.
    clock.now = 0.100
    assert pulse.poll() is True
    assert line.edges == [
        (0.0, "high", 21),
        (0.100, "low", 21),
    ]
