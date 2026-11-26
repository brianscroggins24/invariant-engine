"""Validate and evaluate one offline risk decision without ambient state."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import (
    MAX_EMAX,
    MAX_PREC,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    Inexact,
    InvalidOperation,
    Overflow,
)

from .models import (
    EvidenceIssue,
    ObservationKind,
    RiskCheck,
    RiskObservation,
    RiskPolicy,
    RiskProposal,
    RiskReport,
    RiskScope,
    RiskSnapshot,
    RiskStatus,
    RiskValidationError,
)

_ZERO_AGE = timedelta(0)


def _validate_id(value: object, field: str) -> None:
    if type(value) is not str or not value or not value.isprintable() or value != value.strip():
        raise RiskValidationError(f"{field} must be a nonempty, unpadded printable string")


def _validate_scope(scope: RiskScope, field: str) -> None:
    if type(scope) is not RiskScope:
        raise RiskValidationError(f"{field} must be a RiskScope")
    _validate_id(scope.strategy_id, f"{field}.strategy_id")
    _validate_id(scope.scope_id, f"{field}.scope_id")
    if type(scope.leg_ids) is not tuple or len(scope.leg_ids) != 2:
        raise RiskValidationError(f"{field}.leg_ids must be an ordered tuple of two leg IDs")
    for index, leg_id in enumerate(scope.leg_ids):
        _validate_id(leg_id, f"{field}.leg_ids[{index}]")
    if scope.leg_ids[0] == scope.leg_ids[1]:
        raise RiskValidationError(f"{field}.leg_ids must be distinct")


def _validate_decimal(value: object, field: str, *, nonnegative: bool = False) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise RiskValidationError(f"{field} must be a finite Decimal")
    if nonnegative and value < 0:
        raise RiskValidationError(f"{field} must be nonnegative")


def _validate_pair(values: tuple[Decimal, Decimal], field: str, *, positive: bool) -> None:
    if type(values) is not tuple or len(values) != 2:
        raise RiskValidationError(f"{field} must be an ordered tuple of two leg-unit values")
    for index, value in enumerate(values):
        _validate_decimal(value, f"{field}[{index}]", nonnegative=not positive)
        if positive and value <= 0:
            raise RiskValidationError(f"{field}[{index}] must be positive")


def _utc(timestamp: datetime, field: str) -> datetime:
    # An exact, fixed-offset timezone avoids ambiguous local times and custom tzinfo code.
    if type(timestamp) is not datetime or type(timestamp.tzinfo) is not timezone:
        raise RiskValidationError(f"{field} must be a datetime with a fixed UTC offset")
    try:
        return timestamp.astimezone(UTC)
    except OverflowError as exc:
        raise RiskValidationError(f"{field} is outside the representable UTC range") from exc


def _validate_proposal(proposal: RiskProposal, field: str) -> RiskProposal:
    if type(proposal) is not RiskProposal:
        raise RiskValidationError(f"{field} must be a RiskProposal")
    scope = proposal.scope
    _validate_scope(scope, f"{field}.scope")
    _validate_pair(proposal.quantities, f"{field}.quantities", positive=True)
    decision_time = _utc(proposal.decision_time, f"{field}.decision_time")
    # The issued report must not share the caller's scope object.
    detached_scope = RiskScope(scope.strategy_id, scope.scope_id, scope.leg_ids)
    return RiskProposal(detached_scope, proposal.quantities, decision_time)


def _match_proposal(binding: RiskProposal, proposal: RiskProposal, field: str) -> None:
    if _validate_proposal(binding, field) != proposal:
        raise RiskValidationError(f"{field} does not match the proposal binding")


def _validate_policy(policy: RiskPolicy, proposal: RiskProposal) -> None:
    if type(policy) is not RiskPolicy:
        raise RiskValidationError("policy must be a RiskPolicy")
    _validate_id(policy.policy_id, "policy.policy_id")
    _validate_id(policy.version, "policy.version")
    _validate_scope(policy.scope, "policy.scope")
    if policy.scope != proposal.scope:
        raise RiskValidationError("policy.scope does not match the proposal scope")
    if policy.strategy_enabled is not None and type(policy.strategy_enabled) is not bool:
        raise RiskValidationError("policy.strategy_enabled must be boolean or None")
    if type(policy.max_observation_age) is not timedelta or policy.max_observation_age < _ZERO_AGE:
        raise RiskValidationError("policy.max_observation_age must be a nonnegative timedelta")
    _validate_decimal(policy.min_edge_usd, "policy.min_edge_usd")
    _validate_pair(policy.leg_caps, "policy.leg_caps", positive=False)
    _validate_decimal(policy.exposure_cap_usd, "policy.exposure_cap_usd", nonnegative=True)


def _validate_observation(
    row: RiskObservation | None, kind: ObservationKind, proposal: RiskProposal
) -> RiskObservation | None:
    if row is None:
        return None
    field = f"snapshot.{kind}"
    if type(row) is not RiskObservation:
        raise RiskValidationError(f"{field} must be a RiskObservation or None")
    if type(row.kind) is not str or row.kind != kind:
        raise RiskValidationError(f"{field} does not match the required observation role")
    _match_proposal(row.bound_proposal, proposal, f"{field}.bound_proposal")
    unit = "boolean" if kind == "kill_switch" else "USD"
    if type(row.unit) is not str or row.unit != unit:
        raise RiskValidationError(f"{field}.unit must be {unit}")
    if row.value is not None:
        if kind == "kill_switch":
            if type(row.value) is not bool:
                raise RiskValidationError(f"{field}.value must be boolean or None")
        else:
            _validate_decimal(row.value, f"{field}.value", nonnegative=kind != "gross_edge_lower")
    observed_at = None if row.observed_at is None else _utc(row.observed_at, f"{field}.observed_at")
    return RiskObservation(kind, proposal, row.value, observed_at, unit)


def _validate_snapshot(
    snapshot: RiskSnapshot, proposal: RiskProposal
) -> dict[ObservationKind, RiskObservation | None]:
    if type(snapshot) is not RiskSnapshot:
        raise RiskValidationError("snapshot must be a RiskSnapshot")
    _match_proposal(snapshot.bound_proposal, proposal, "snapshot.bound_proposal")
    rows: tuple[tuple[ObservationKind, RiskObservation | None], ...] = (
        ("kill_switch", snapshot.kill_switch),
        ("gross_edge_lower", snapshot.gross_edge_lower),
        ("costs_upper", snapshot.costs_upper),
        ("existing_exposure", snapshot.existing_exposure),
        ("loss_if_a_fails", snapshot.loss_if_a_fails),
        ("loss_if_b_fails", snapshot.loss_if_b_fails),
    )
    return {kind: _validate_observation(row, kind, proposal) for kind, row in rows}


@dataclass(frozen=True, slots=True)
class _Evidence:
    value: bool | Decimal | None
    age: timedelta | None
    issues: tuple[EvidenceIssue, ...]


def _assess_evidence(
    kind: ObservationKind,
    row: RiskObservation | None,
    decision_time: datetime,
    max_age: timedelta,
) -> _Evidence:
    if row is None:
        return _Evidence(None, None, (EvidenceIssue(kind, "missing_observation"),))

    issues = []
    age = None
    if row.observed_at is None:
        issues.append(EvidenceIssue(kind, "missing_timestamp"))
    else:
        age = decision_time - row.observed_at
        if age < _ZERO_AGE:
            issues.append(EvidenceIssue(kind, "future_dated"))
        elif age > max_age:
            issues.append(EvidenceIssue(kind, "stale"))
    if row.value is None:
        issues.append(EvidenceIssue(kind, "unknown_value"))
    return _Evidence(row.value, age, tuple(issues))


def _exact_sum(left: Decimal, right: Decimal) -> Decimal:
    # Align both coefficients and allow a carry. Zeros need no alignment,
    # regardless of their stored exponent. Do not consult the ambient context.
    if left.is_zero():
        return right
    if right.is_zero():
        return left
    exponent = min(left.as_tuple().exponent, right.as_tuple().exponent)
    assert isinstance(exponent, int)  # both operands were validated as finite
    precision = max(left.adjusted(), right.adjusted()) - exponent + 2
    context = Context(
        prec=min(precision, MAX_PREC),
        rounding=ROUND_HALF_EVEN,
        Emin=MIN_EMIN,
        Emax=MAX_EMAX,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[Inexact, InvalidOperation, Overflow],
    )
    try:
        return context.add(left, right)
    except (DecimalException, MemoryError) as exc:
        raise RiskValidationError("required exact USD total cannot be represented") from exc


def _check_enablement(enabled: bool | None) -> RiskCheck:
    if enabled is True:
        return RiskCheck(
            "strategy_enablement", "PASS", enabled, "boolean", True, "strategy_enabled"
        )
    return RiskCheck(
        "strategy_enablement",
        "BLOCK",
        enabled,
        "boolean",
        True,
        "strategy_disabled" if enabled is False else "enablement_not_explicit",
    )


def _check_switch(evidence: _Evidence) -> RiskCheck:
    if evidence.value is True:
        return RiskCheck(
            "kill_switch",
            "BLOCK",
            True,
            "boolean",
            False,
            "switch_active",
            evidence_issues=evidence.issues,
        )
    if evidence.issues:
        return RiskCheck(
            "kill_switch",
            "BLOCK",
            evidence.value,
            "boolean",
            False,
            "unusable_evidence",
            evidence_issues=evidence.issues,
        )
    return RiskCheck("kill_switch", "PASS", False, "boolean", False, "switch_clear")


def _check_edge(gross: _Evidence, costs: _Evidence, limit: Decimal) -> RiskCheck:
    issues = gross.issues + costs.issues
    if issues:
        return RiskCheck(
            "minimum_edge", "BLOCK", None, "USD", limit, "unusable_evidence", evidence_issues=issues
        )
    assert type(gross.value) is Decimal and type(costs.value) is Decimal
    edge = _exact_sum(gross.value, costs.value.copy_negate())
    passes = edge >= limit
    return RiskCheck(
        "minimum_edge",
        "PASS" if passes else "BLOCK",
        edge,
        "USD",
        limit,
        "at_least_minimum" if passes else "below_minimum",
    )


def _check_size(leg_id: str, quantity: Decimal, cap: Decimal) -> RiskCheck:
    passes = quantity <= cap
    return RiskCheck(
        "leg_size",
        "PASS" if passes else "BLOCK",
        quantity,
        "units",
        cap,
        "within_cap" if passes else "above_cap",
        leg_id=leg_id,
    )


def _check_exposure(existing: _Evidence, a: _Evidence, b: _Evidence, cap: Decimal) -> RiskCheck:
    issues = existing.issues + a.issues + b.issues
    if issues:
        return RiskCheck(
            "exposure", "BLOCK", None, "USD", cap, "unusable_evidence", evidence_issues=issues
        )
    assert type(existing.value) is Decimal and type(a.value) is Decimal and type(b.value) is Decimal
    total = _exact_sum(existing.value, max(a.value, b.value))
    passes = total <= cap
    return RiskCheck(
        "exposure",
        "PASS" if passes else "BLOCK",
        total,
        "USD",
        cap,
        "within_cap" if passes else "above_cap",
    )


def evaluate_risk(proposal: RiskProposal, policy: RiskPolicy, snapshot: RiskSnapshot) -> RiskReport:
    """Report all checks, or raise RiskValidationError for malformed input.

    Check order is enablement, switch, six freshness checks in snapshot order,
    edge, both sizes in leg order, then exposure. A PASS is not authorization.
    """
    try:
        bound = _validate_proposal(proposal, "proposal")
        _validate_policy(policy, bound)
        rows = _validate_snapshot(snapshot, bound)
    except AttributeError as exc:
        raise RiskValidationError("risk input contains an uninitialized field") from exc

    max_age = policy.max_observation_age
    evidence = {
        kind: _assess_evidence(kind, row, bound.decision_time, max_age)
        for kind, row in rows.items()
    }
    checks = (
        _check_enablement(policy.strategy_enabled),
        _check_switch(evidence["kill_switch"]),
        *(
            RiskCheck(
                "freshness",
                "BLOCK" if item.issues else "PASS",
                item.age,
                "duration",
                max_age,
                "unusable_evidence" if item.issues else "fresh",
                observation=kind,
                evidence_issues=item.issues,
            )
            for kind, item in evidence.items()
        ),
        _check_edge(evidence["gross_edge_lower"], evidence["costs_upper"], policy.min_edge_usd),
        *(
            _check_size(leg_id, quantity, cap)
            for leg_id, quantity, cap in zip(
                bound.scope.leg_ids, bound.quantities, policy.leg_caps, strict=True
            )
        ),
        _check_exposure(
            evidence["existing_exposure"],
            evidence["loss_if_a_fails"],
            evidence["loss_if_b_fails"],
            policy.exposure_cap_usd,
        ),
    )
    status: RiskStatus = "PASS" if all(check.status == "PASS" for check in checks) else "BLOCK"
    return RiskReport(status, bound, policy.policy_id, policy.version, checks)
