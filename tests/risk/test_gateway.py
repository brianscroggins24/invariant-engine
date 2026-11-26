from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, getcontext, localcontext

import pytest

from invariant_engine.capture import is_trusted_attempt, is_trusted_batch
from invariant_engine.constraints.models import is_trusted_constraint, is_trusted_observation
from invariant_engine.diagnostics import is_trusted_historical_validation_record
from invariant_engine.discovery import DiscoveryResult
from invariant_engine.opportunities import is_trusted_candidate
from invariant_engine.risk import (
    EvidenceIssue,
    RiskCheck,
    RiskObservation,
    RiskPolicy,
    RiskProposal,
    RiskScope,
    RiskSnapshot,
    RiskValidationError,
    evaluate_risk,
)
from invariant_engine.simulation import (
    CutoffKnowledge,
    ScenarioSpec,
    ScenarioValidationError,
    evaluate_scenario,
)

_TIME = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
_AGE = timedelta(seconds=10)
_TICK = timedelta(microseconds=1)
_SCOPE = RiskScope("strategy", "synthetic-book", ("yes-at-A", "no-at-B"))
_PROPOSAL = RiskProposal(_SCOPE, (Decimal("2"), Decimal("3")), _TIME)
_POLICY = RiskPolicy(
    "risk-policy",
    "v1",
    _SCOPE,
    True,
    _AGE,
    Decimal("1.00"),
    (Decimal("3"), Decimal("4")),
    Decimal("4.00"),
)
_KINDS = (
    "kill_switch",
    "gross_edge_lower",
    "costs_upper",
    "existing_exposure",
    "loss_if_a_fails",
    "loss_if_b_fails",
)
_VALUES = (
    False,
    Decimal("1.50"),
    Decimal("0.20"),
    Decimal("3.00"),
    Decimal("0.40"),
    Decimal("0.70"),
)


def _snapshot(proposal=_PROPOSAL, age=timedelta(seconds=1)):
    return RiskSnapshot(
        proposal,
        **{
            kind: RiskObservation(
                kind,
                proposal,
                value,
                proposal.decision_time - age,
                "boolean" if kind == "kill_switch" else "USD",
            )
            for kind, value in zip(_KINDS, _VALUES, strict=True)
        },
    )


def _change(snapshot, kind, **changes):
    return replace(snapshot, **{kind: replace(getattr(snapshot, kind), **changes)})


def _check(report, name, *, observation=None, leg_id=None):
    (match,) = (
        item
        for item in report.checks
        if (item.name, item.observation, item.leg_id) == (name, observation, leg_id)
    )
    return match


def test_all_pass_has_complete_ordered_repeatable_non_actionable_report():
    report = evaluate_risk(_PROPOSAL, _POLICY, _snapshot())
    assert report == evaluate_risk(replace(_PROPOSAL), replace(_POLICY), _snapshot())
    assert report.status == "PASS"
    assert report.proposal == _PROPOSAL
    assert (report.policy_id, report.policy_version) == ("risk-policy", "v1")
    assert report.actionable is report.reserves_capital is False
    assert report.checks == (
        RiskCheck("strategy_enablement", "PASS", True, "boolean", True, "strategy_enabled"),
        RiskCheck("kill_switch", "PASS", False, "boolean", False, "switch_clear"),
        *(
            RiskCheck("freshness", "PASS", timedelta(seconds=1), "duration", _AGE, "fresh", kind)
            for kind in _KINDS
        ),
        RiskCheck(
            "minimum_edge", "PASS", Decimal("1.30"), "USD", Decimal("1.00"), "at_least_minimum"
        ),
        RiskCheck(
            "leg_size", "PASS", Decimal("2"), "units", Decimal("3"), "within_cap", leg_id="yes-at-A"
        ),
        RiskCheck(
            "leg_size", "PASS", Decimal("3"), "units", Decimal("4"), "within_cap", leg_id="no-at-B"
        ),
        RiskCheck("exposure", "PASS", Decimal("3.70"), "USD", Decimal("4.00"), "within_cap"),
    )


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    ("age", "reason"),
    [
        (timedelta(0), None),
        (_AGE, None),
        (_AGE + _TICK, "stale"),
        (-_TICK, "future_dated"),
        (None, "missing_timestamp"),
    ],
)
def test_every_observation_freshness_boundary_and_dependent_check(kind, age, reason):
    observed_at = None if age is None else _TIME - age
    report = evaluate_risk(_PROPOSAL, _POLICY, _change(_snapshot(), kind, observed_at=observed_at))
    result = _check(report, "freshness", observation=kind)
    expected = "PASS" if reason is None else "BLOCK"
    assert report.status == result.status == expected
    assert (result.value, result.unit, result.limit) == (age, "duration", _AGE)
    assert result.evidence_issues == (() if reason is None else (EvidenceIssue(kind, reason),))
    dependent = _check(report, _dependent(kind))
    assert dependent.status == expected
    if reason is not None:
        assert dependent.evidence_issues == result.evidence_issues
        assert dependent.value is (False if kind == "kill_switch" else None)


def _dependent(kind):
    if kind == "kill_switch":
        return "kill_switch"
    if kind in ("gross_edge_lower", "costs_upper"):
        return "minimum_edge"
    return "exposure"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("reason", ["missing_observation", "unknown_value"])
def test_required_missing_or_unknown_evidence_blocks_without_a_default(kind, reason):
    snapshot = _snapshot()
    if reason == "missing_observation":
        snapshot = replace(snapshot, **{kind: None})
    else:
        snapshot = _change(snapshot, kind, value=None)
    report = evaluate_risk(_PROPOSAL, _POLICY, snapshot)
    freshness = _check(report, "freshness", observation=kind)
    dependent = _check(report, _dependent(kind))
    assert report.status == freshness.status == dependent.status == "BLOCK"
    assert dependent.value is None
    assert dependent.evidence_issues == freshness.evidence_issues == (EvidenceIssue(kind, reason),)


@pytest.mark.parametrize(
    ("enabled", "reason"), [(False, "strategy_disabled"), (None, "enablement_not_explicit")]
)
def test_non_enabled_strategy_blocks(enabled, reason):
    report = evaluate_risk(_PROPOSAL, replace(_POLICY, strategy_enabled=enabled), _snapshot())
    assert report.status == "BLOCK"
    assert [check for check in report.checks if check.status == "BLOCK"] == [
        RiskCheck("strategy_enablement", "BLOCK", enabled, "boolean", True, reason)
    ]


def test_active_switch_blocks_despite_high_edge_and_fresh_state():
    snapshot = _change(_snapshot(), "gross_edge_lower", value=Decimal("99"))
    report = evaluate_risk(_PROPOSAL, _POLICY, _change(snapshot, "kill_switch", value=True))
    assert report.status == "BLOCK"
    assert _check(report, "minimum_edge").value == Decimal("98.80")
    assert [check for check in report.checks if check.status == "BLOCK"] == [
        RiskCheck("kill_switch", "BLOCK", True, "boolean", False, "switch_active")
    ]


@pytest.mark.parametrize("leg", [0, 1])
@pytest.mark.parametrize(
    ("offset", "expected"), [(Decimal("0"), "PASS"), (Decimal("0.0001"), "BLOCK")]
)
def test_each_quantity_at_and_just_beyond_its_own_cap(leg, offset, expected):
    quantities = list(_PROPOSAL.quantities)
    quantities[leg] = _POLICY.leg_caps[leg] + offset
    proposal = replace(_PROPOSAL, quantities=tuple(quantities))
    report = evaluate_risk(proposal, _POLICY, _snapshot(proposal))
    check = _check(report, "leg_size", leg_id=_SCOPE.leg_ids[leg])
    assert report.status == check.status == expected
    assert (check.value, check.unit, check.limit) == (
        quantities[leg],
        "units",
        _POLICY.leg_caps[leg],
    )
    assert _check(report, "leg_size", leg_id=_SCOPE.leg_ids[1 - leg]).status == "PASS"


@pytest.mark.parametrize(
    ("gross", "cost", "floor", "net", "expected"),
    [
        ("1.20", "0.20", "1.00", "1.00", "PASS"),
        ("1.1999999", "0.20", "1.00", "0.9999999", "BLOCK"),
        ("-0.25", "0.5", "-0.75", "-0.75", "PASS"),
        ("-0.25", "0.5000001", "-0.75", "-0.7500001", "BLOCK"),
    ],
)
def test_conservative_total_edge_uses_cost_upper_bound_and_signed_gross(
    gross, cost, floor, net, expected
):
    snapshot = _change(_snapshot(), "gross_edge_lower", value=Decimal(gross))
    snapshot = _change(snapshot, "costs_upper", value=Decimal(cost))
    report = evaluate_risk(_PROPOSAL, replace(_POLICY, min_edge_usd=Decimal(floor)), snapshot)
    check = _check(report, "minimum_edge")
    assert report.status == check.status == expected
    assert (check.value, check.unit, check.limit) == (Decimal(net), "USD", Decimal(floor))


@pytest.mark.parametrize("larger", ["loss_if_a_fails", "loss_if_b_fails"])
@pytest.mark.parametrize(
    ("loss", "total", "expected"), [("1.00", "4.00", "PASS"), ("1.000001", "4.000001", "BLOCK")]
)
def test_exposure_uses_larger_not_sum_or_average(larger, loss, total, expected):
    snapshot = _change(_snapshot(), larger, value=Decimal(loss))
    report = evaluate_risk(_PROPOSAL, _POLICY, snapshot)
    check = _check(report, "exposure")
    assert report.status == check.status == expected
    assert (check.value, check.unit, check.limit) == (Decimal(total), "USD", Decimal("4.00"))


def test_multiple_failures_report_all_checks_and_all_unusable_dependencies():
    proposal = replace(_PROPOSAL, quantities=(Decimal("3.1"), Decimal("4.1")))
    snapshot = replace(_snapshot(proposal), loss_if_a_fails=None)
    snapshot = _change(snapshot, "kill_switch", value=True, observed_at=_TIME + _TICK)
    snapshot = _change(snapshot, "gross_edge_lower", value=None, observed_at=None)
    snapshot = _change(snapshot, "costs_upper", observed_at=_TIME - _AGE - _TICK)
    snapshot = _change(snapshot, "loss_if_b_fails", value=None)
    report = evaluate_risk(proposal, replace(_POLICY, strategy_enabled=False), snapshot)
    assert report.status == "BLOCK"
    assert [check.name for check in report.checks if check.status == "PASS"] == ["freshness"]
    assert _check(report, "freshness", observation="existing_exposure").status == "PASS"
    assert _check(report, "kill_switch") == RiskCheck(
        "kill_switch",
        "BLOCK",
        True,
        "boolean",
        False,
        "switch_active",
        evidence_issues=(EvidenceIssue("kill_switch", "future_dated"),),
    )
    assert _check(report, "minimum_edge") == RiskCheck(
        "minimum_edge",
        "BLOCK",
        None,
        "USD",
        Decimal("1.00"),
        "unusable_evidence",
        evidence_issues=(
            EvidenceIssue("gross_edge_lower", "missing_timestamp"),
            EvidenceIssue("gross_edge_lower", "unknown_value"),
            EvidenceIssue("costs_upper", "stale"),
        ),
    )
    assert _check(report, "exposure") == RiskCheck(
        "exposure",
        "BLOCK",
        None,
        "USD",
        Decimal("4.00"),
        "unusable_evidence",
        evidence_issues=(
            EvidenceIssue("loss_if_a_fails", "missing_observation"),
            EvidenceIssue("loss_if_b_fails", "unknown_value"),
        ),
    )


@pytest.mark.parametrize(
    "scope",
    [
        replace(_SCOPE, strategy_id="other"),
        replace(_SCOPE, scope_id="other"),
        replace(_SCOPE, leg_ids=("yes-at-A", "other")),
        replace(_SCOPE, leg_ids=tuple(reversed(_SCOPE.leg_ids))),
    ],
)
def test_cross_scope_swap_rejected_by_policy_top_level_snapshot_and_each_row(scope):
    substituted = replace(_PROPOSAL, scope=scope)
    with pytest.raises(RiskValidationError, match=r"policy\.scope.*match"):
        evaluate_risk(substituted, _POLICY, _snapshot(substituted))
    with pytest.raises(RiskValidationError, match=r"snapshot\.bound_proposal.*match"):
        evaluate_risk(_PROPOSAL, _POLICY, _snapshot(substituted))
    for kind in _KINDS:
        with pytest.raises(RiskValidationError, match=rf"snapshot\.{kind}\.bound_proposal.*match"):
            evaluate_risk(
                _PROPOSAL, _POLICY, _change(_snapshot(), kind, bound_proposal=substituted)
            )


@pytest.mark.parametrize(
    "proposal",
    [
        replace(_PROPOSAL, quantities=(Decimal("2.1"), Decimal("3"))),
        replace(_PROPOSAL, decision_time=_TIME + _TICK),
    ],
)
def test_cross_quantity_or_time_swap_rejected_at_snapshot_and_observation_level(proposal):
    with pytest.raises(RiskValidationError, match=r"snapshot\.bound_proposal.*match"):
        evaluate_risk(proposal, _POLICY, _snapshot())
    for kind in _KINDS:
        with pytest.raises(RiskValidationError, match=rf"snapshot\.{kind}\.bound_proposal.*match"):
            evaluate_risk(
                proposal, _POLICY, _change(_snapshot(proposal), kind, bound_proposal=_PROPOSAL)
            )


def test_duplicate_or_swapped_case_and_cost_rows_rejected():
    snapshot = _snapshot()
    invalid = (
        replace(snapshot, loss_if_a_fails=snapshot.loss_if_b_fails),
        replace(snapshot, loss_if_b_fails=snapshot.loss_if_a_fails),
        replace(snapshot, costs_upper=snapshot.gross_edge_lower),
    )
    for candidate in invalid:
        with pytest.raises(RiskValidationError, match="observation role"):
            evaluate_risk(_PROPOSAL, _POLICY, candidate)


@pytest.mark.parametrize(
    "value", [True, 1, 1.5, "1", Decimal("NaN"), Decimal("sNaN"), Decimal("-Infinity")]
)
def test_malformed_numbers_rejected_everywhere_even_with_disabled_strategy(value):
    policy = replace(_POLICY, strategy_enabled=False)
    snapshot = _snapshot()
    candidates = [
        (replace(_PROPOSAL, quantities=(value, Decimal("3"))), policy, snapshot),
        (_PROPOSAL, replace(policy, min_edge_usd=value), snapshot),
        (_PROPOSAL, replace(policy, leg_caps=(Decimal("0"), value)), snapshot),
        (_PROPOSAL, replace(policy, exposure_cap_usd=value), snapshot),
        *((_PROPOSAL, policy, _change(snapshot, kind, value=value)) for kind in _KINDS[1:]),
    ]
    for args in candidates:
        with pytest.raises(RiskValidationError, match="finite Decimal"):
            evaluate_risk(*args)


def test_malformed_ranges_types_uninitialized_fields_and_units_rejected():
    class MutableProposal(RiskProposal):
        pass

    class LookalikeUnit(str):
        pass

    snapshot = _snapshot()
    invalid = (
        (replace(_PROPOSAL, scope=replace(_SCOPE, leg_ids=("same", "same"))), _POLICY, snapshot),
        (replace(_PROPOSAL, scope=replace(_SCOPE, strategy_id="")), _POLICY, snapshot),
        (replace(_PROPOSAL, quantities=list(_PROPOSAL.quantities)), _POLICY, snapshot),
        (replace(_PROPOSAL, quantities=(Decimal("0"), Decimal("3"))), _POLICY, snapshot),
        (replace(_PROPOSAL, decision_time=_TIME.replace(tzinfo=None)), _POLICY, snapshot),
        (MutableProposal(_SCOPE, _PROPOSAL.quantities, _TIME), _POLICY, snapshot),
        (_PROPOSAL, object.__new__(RiskPolicy), snapshot),
        (_PROPOSAL, replace(_POLICY, version=""), snapshot),
        (_PROPOSAL, replace(_POLICY, max_observation_age=-_TICK), snapshot),
        (_PROPOSAL, replace(_POLICY, max_observation_age=10), snapshot),
        (_PROPOSAL, replace(_POLICY, strategy_enabled=1), snapshot),
        (_PROPOSAL, replace(_POLICY, exposure_cap_usd=Decimal("-0.1")), snapshot),
        (_PROPOSAL, replace(_POLICY, leg_caps=(Decimal("3"), Decimal("-0.1"))), snapshot),
        (_PROPOSAL, _POLICY, _change(snapshot, "kill_switch", value=0)),
        (_PROPOSAL, _POLICY, _change(snapshot, "kill_switch", unit="USD")),
        (_PROPOSAL, _POLICY, _change(snapshot, "costs_upper", unit="EUR")),
        (_PROPOSAL, _POLICY, _change(snapshot, "costs_upper", unit=LookalikeUnit("USD"))),
        (_PROPOSAL, _POLICY, _change(snapshot, "gross_edge_lower", observed_at=_TIME.date())),
        (
            _PROPOSAL,
            _POLICY,
            _change(snapshot, "gross_edge_lower", observed_at=_TIME.replace(tzinfo=None)),
        ),
        *(
            (_PROPOSAL, _POLICY, _change(snapshot, kind, value=Decimal("-0.1")))
            for kind in _KINDS[2:]
        ),
    )
    for args in invalid:
        with pytest.raises(RiskValidationError):
            evaluate_risk(*args)


def test_offset_representations_are_normalized_and_zero_max_age_is_inclusive():
    offset = timezone(timedelta(hours=-4))
    local_proposal = replace(_PROPOSAL, decision_time=_TIME.astimezone(offset))
    policy = replace(_POLICY, max_observation_age=timedelta(0))
    report = evaluate_risk(_PROPOSAL, policy, _snapshot(local_proposal, age=timedelta(0)))
    assert report.status == "PASS"
    assert report == evaluate_risk(local_proposal, policy, _snapshot(_PROPOSAL, age=timedelta(0)))
    assert report.proposal.decision_time.tzinfo is UTC
    assert evaluate_risk(_PROPOSAL, policy, _snapshot(age=_TICK)).status == "BLOCK"


def test_zero_caps_and_known_zero_costs_and_losses_are_not_missing():
    policy = replace(_POLICY, exposure_cap_usd=Decimal(0), leg_caps=(Decimal(0), Decimal("4")))
    snapshot = _snapshot()
    for kind in _KINDS[2:]:
        snapshot = _change(snapshot, kind, value=Decimal("0E-1000000"))
    report = evaluate_risk(_PROPOSAL, policy, snapshot)
    assert report.status == "BLOCK"
    assert _check(report, "exposure").value == 0
    assert _check(report, "minimum_edge").value == Decimal("1.50")
    assert [check for check in report.checks if check.status == "BLOCK"] == [
        RiskCheck(
            "leg_size", "BLOCK", Decimal("2"), "units", Decimal(0), "above_cap", leg_id="yes-at-A"
        )
    ]


@pytest.mark.parametrize("rounding", [ROUND_CEILING, ROUND_FLOOR])
@pytest.mark.parametrize("all_traps", [False, True])
def test_exact_arithmetic_and_context_isolation_at_adjacent_values(rounding, all_traps):
    policy = replace(
        _POLICY,
        min_edge_usd=Decimal("1"),
        exposure_cap_usd=Decimal("10000000000000000000000000000000000.0000000000001"),
    )
    snapshot = _change(
        _snapshot(), "gross_edge_lower", value=Decimal("1.00000000000000000000000000000001")
    )
    snapshot = _change(snapshot, "costs_upper", value=Decimal("1E-32"))
    snapshot = _change(snapshot, "existing_exposure", value=Decimal("1E+34"))
    snapshot = _change(snapshot, "loss_if_a_fails", value=Decimal("0"))
    snapshot = _change(snapshot, "loss_if_b_fails", value=Decimal("1E-13"))
    reference = evaluate_risk(_PROPOSAL, policy, snapshot)
    with localcontext() as context:
        context.prec = 1
        context.rounding = rounding
        context.Emin = -1
        context.Emax = 1
        context.clamp = 1
        for signal in context.traps:
            context.traps[signal] = all_traps
            context.flags[signal] = True
        state = repr(context)
        accepted = evaluate_risk(_PROPOSAL, policy, snapshot)
        assert accepted.status == "PASS"
        assert accepted == reference
        beyond = _change(snapshot, "costs_upper", value=Decimal("1.1E-32"))
        beyond = _change(beyond, "loss_if_b_fails", value=Decimal("1.1E-13"))
        rejected = evaluate_risk(_PROPOSAL, policy, beyond)
        assert rejected.status == "BLOCK"
        assert [check.name for check in rejected.checks if check.status == "BLOCK"] == [
            "minimum_edge",
            "exposure",
        ]
        assert _check(rejected, "minimum_edge").value == Decimal(
            "0.999999999999999999999999999999999"
        )
        assert _check(rejected, "exposure").value == Decimal(
            "10000000000000000000000000000000000.00000000000011"
        )
        assert getcontext() is context and repr(context) == state


def test_no_proposal_overrides_and_report_and_inputs_are_deeply_immutable():
    snapshot = _change(_snapshot(), "costs_upper", value=None)
    report = evaluate_risk(_PROPOSAL, _POLICY, snapshot)
    for value, field in (
        (_PROPOSAL, "quantities"),
        (_POLICY, "leg_caps"),
        (_SCOPE, "leg_ids"),
        (snapshot, "costs_upper"),
        (snapshot.costs_upper, "value"),
        (report, "checks"),
        (report.proposal.scope, "scope_id"),
        (report.checks[0], "status"),
        (_check(report, "minimum_edge").evidence_issues[0], "reason"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, None)
    assert all(
        type(value) is tuple
        for value in (
            _PROPOSAL.quantities,
            _POLICY.leg_caps,
            _SCOPE.leg_ids,
            report.checks,
            _check(report, "minimum_edge").evidence_issues,
        )
    )
    for field in (
        "strategy_enabled",
        "kill_switch",
        "min_edge_usd",
        "exposure_cap_usd",
        "leg_caps",
        "costs_upper",
    ):
        assert not hasattr(_PROPOSAL, field)
        with pytest.raises(TypeError):
            replace(_PROPOSAL, **{field: 0})


def test_issued_report_keeps_its_scope_when_caller_reinitializes_the_input_scope():
    scope = RiskScope("alpha", "original-scope", ("north", "south"))
    proposal = replace(_PROPOSAL, scope=scope)
    policy = replace(_POLICY, scope=scope)
    report = evaluate_risk(proposal, policy, _snapshot(proposal))
    assert report.status == "PASS"

    scope.__init__("beta", "replacement-scope", ("east", "west"))

    assert proposal.scope == RiskScope("beta", "replacement-scope", ("east", "west"))
    assert report.status == "PASS"
    assert report.proposal.scope == RiskScope("alpha", "original-scope", ("north", "south"))
    assert tuple(check.leg_id for check in report.checks if check.name == "leg_size") == (
        "north",
        "south",
    )


def test_risk_material_cannot_transfer_trust_and_earlier_objects_are_not_risk_inputs():
    snapshot = _snapshot()
    report = evaluate_risk(_PROPOSAL, _POLICY, snapshot)
    for material in (_PROPOSAL, _POLICY, snapshot, report):
        assert not is_trusted_candidate(material)
        assert not is_trusted_historical_validation_record(material)
        assert not is_trusted_constraint(material)
        assert not is_trusted_observation(material)
        assert not is_trusted_attempt(material)
        assert not is_trusted_batch(material)
        assert not isinstance(material, DiscoveryResult)
        with pytest.raises(ScenarioValidationError):
            evaluate_scenario(material)
    cutoff = CutoffKnowledge(True)
    simulation = evaluate_scenario(ScenarioSpec(Decimal(1), Decimal(2), (), cutoff, cutoff))
    for wrong in (simulation, report, {"bound_proposal": _PROPOSAL}):
        for args in (
            (wrong, _POLICY, snapshot),
            (_PROPOSAL, wrong, snapshot),
            (_PROPOSAL, _POLICY, wrong),
        ):
            with pytest.raises(RiskValidationError):
                evaluate_risk(*args)
