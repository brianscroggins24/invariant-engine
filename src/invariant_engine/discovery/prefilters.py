"""Conservative deterministic search-reduction signals."""

from __future__ import annotations

from invariant_engine.discovery.schema import (
    DiscoveryInput,
    PrefilterEvaluation,
    PrefilterName,
    PrefilterPolicy,
    PrefilterSignal,
    PrefilterStatus,
)


def _labels(values: tuple[str, ...]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _label_signal(
    name: PrefilterName, left: tuple[str, ...], right: tuple[str, ...]
) -> PrefilterSignal:
    if not left or not right:
        return PrefilterSignal(
            name, PrefilterStatus.NOT_APPLICABLE, "required label metadata missing"
        )
    left_set = _labels(left)
    right_set = _labels(right)
    overlap = left_set & right_set
    status = PrefilterStatus.PASS if overlap else PrefilterStatus.FAIL
    return PrefilterSignal(
        name,
        status,
        "exact normalized label intersection"
        if overlap
        else "no exact normalized label intersection",
        ",".join(sorted(left_set)),
        ",".join(sorted(right_set)),
    )


def _date_signal(left: DiscoveryInput, right: DiscoveryInput) -> PrefilterSignal:
    if left.end_date is None or right.end_date is None:
        return PrefilterSignal(
            PrefilterName.DATE, PrefilterStatus.NOT_APPLICABLE, "end date missing"
        )
    status = PrefilterStatus.PASS if left.end_date == right.end_date else PrefilterStatus.FAIL
    return PrefilterSignal(
        PrefilterName.DATE,
        status,
        "exact supplied end-date equality"
        if status is PrefilterStatus.PASS
        else "end dates differ",
        left.end_date.isoformat(),
        right.end_date.isoformat(),
    )


def _threshold_signal(left: DiscoveryInput, right: DiscoveryInput) -> PrefilterSignal:
    if not left.thresholds or not right.thresholds:
        return PrefilterSignal(
            PrefilterName.THRESHOLD,
            PrefilterStatus.NOT_APPLICABLE,
            "threshold metadata missing",
        )
    left_values = {(item.comparator, item.value) for item in left.thresholds}
    right_values = {(item.comparator, item.value) for item in right.thresholds}
    overlap = left_values & right_values
    status = PrefilterStatus.PASS if overlap else PrefilterStatus.FAIL
    return PrefilterSignal(
        PrefilterName.THRESHOLD,
        status,
        "exact Decimal comparator/value match"
        if status is PrefilterStatus.PASS
        else "no exact Decimal comparator/value match",
        ",".join(f"{comparator}{value}" for comparator, value in sorted(left_values)),
        ",".join(f"{comparator}{value}" for comparator, value in sorted(right_values)),
    )


def _unit_signal(left: DiscoveryInput, right: DiscoveryInput) -> PrefilterSignal:
    if left.unit is None or right.unit is None:
        return PrefilterSignal(
            PrefilterName.UNIT, PrefilterStatus.NOT_APPLICABLE, "unit metadata missing"
        )
    left_unit = left.unit.strip().casefold()
    right_unit = right.unit.strip().casefold()
    status = PrefilterStatus.PASS if left_unit == right_unit else PrefilterStatus.FAIL
    return PrefilterSignal(
        PrefilterName.UNIT,
        status,
        "exact normalized unit equality" if status is PrefilterStatus.PASS else "units differ",
        left_unit,
        right_unit,
    )


def evaluate_prefilters(
    left: DiscoveryInput, right: DiscoveryInput, policy: PrefilterPolicy
) -> PrefilterEvaluation:
    """Evaluate every v1 signal; only explicitly selected signals gate results."""

    signals = (
        _label_signal(PrefilterName.TOPIC, left.topics, right.topics),
        _label_signal(PrefilterName.ENTITY, left.entities, right.entities),
        _date_signal(left, right),
        _threshold_signal(left, right),
        _unit_signal(left, right),
    )
    by_name = {signal.name: signal for signal in signals}
    required_passed = all(
        by_name[name].status is PrefilterStatus.PASS for name in policy.required_signals
    )
    return PrefilterEvaluation(left.input_id, right.input_id, signals, required_passed)


__all__ = ["evaluate_prefilters"]
