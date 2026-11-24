from dataclasses import FrozenInstanceError, replace
from decimal import ROUND_DOWN, ROUND_UP, Decimal, Inexact, getcontext, localcontext

import pytest

from invariant_engine import simulation
from invariant_engine.simulation import (
    CutoffKnowledge,
    HypotheticalPayout,
    ScenarioEvent,
    ScenarioSpec,
    ScenarioValidationError,
    evaluate_scenario,
)
from invariant_engine.simulation.queue import evaluate_queue_scenario
from invariant_engine.simulation.queue_models import (
    ArrivalTrace,
    Cancellation,
    QueueLegSpec,
    QueueScenarioSpec,
    SellArrival,
)

D = Decimal
_OPEN = QueueLegSpec(D(5), D("0.45"), 2, 3, "open", D(3))
_REJECT = QueueLegSpec(D(4), D("0.75"), 1, 1, "reject", None)
_SALE = SellArrival(20, D(6))
_MIDDLE = replace(_OPEN, arrivals=(_SALE,), cancellation=Cancellation(25, 5))
_SPEC = QueueScenarioSpec(_REJECT, _MIDDLE, 31, (HypotheticalPayout("B pays", D(0), D("1.20")),))


def _check_replay(spec):
    """Replay the published events, and reconcile the independent per-arrival ledger."""
    result = evaluate_queue_scenario(spec)
    complete = CutoffKnowledge(True, True)
    assert result.accounting == evaluate_scenario(
        ScenarioSpec(
            spec.leg_a.quantity,
            spec.leg_b.quantity,
            result.events,
            complete,
            complete,
            spec.payout_table,
        )
    )
    assert result.conditional and not result.actionable
    assert result.accounting.conditional and not result.accounting.actionable
    for row in result.trace:
        assert row.time_ms <= spec.cutoff_ms
        assert min(row.consumed_ahead, row.filled, row.unused) >= 0
        assert row.volume == row.consumed_ahead + row.filled + row.unused
    emitted = tuple(e for e in result.events if e.kind == "fill")
    assert [(e.leg, e.quantity) for e in emitted] == [
        (r.leg, r.filled) for r in result.trace if r.filled
    ]
    for leg, cutoff in (("A", result.accounting.leg_a), ("B", result.accounting.leg_b)):
        assert sum(r.filled for r in result.trace if r.leg == leg) == cutoff.acquired_quantity
    return result


@pytest.mark.parametrize(
    ("ahead", "cancel", "filled", "canceled", "consumed", "unused"),
    [
        (3, Cancellation(5, 5, request_order=1), 0, 5, 0, 6),
        (3, Cancellation(25, 5), 3, 2, 3, 0),
        (8, Cancellation(25, 5), 0, 5, 6, 0),
    ],
)
def test_approved_queue_and_delay_comparisons(ahead, cancel, filled, canceled, consumed, unused):
    b = replace(_MIDDLE, ahead_at_open=D(ahead), cancellation=cancel, outcome_order=0)
    result = _check_replay(replace(_SPEC, leg_b=b))
    assert result.trace == (ArrivalTrace("B", 20, None, D(6), D(consumed), D(filled), D(unused)),)
    assert result.accounting.leg_b.status == "canceled"
    assert result.accounting.leg_b.acquired_quantity == filled
    assert result.accounting.leg_b.closed_unfilled_quantity == canceled
    assert result.accounting.gross_cost_usd == D(filled) * b.price_usd
    assert result.accounting.payouts[0].gross_payout_usd == D(filled) * D("1.20")


def test_changing_only_opening_delay_moves_sale_before_entry():
    b = replace(_MIDDLE, processing_delay_ms=19)
    result = _check_replay(replace(_SPEC, leg_b=b))
    assert result.trace == (ArrivalTrace("B", 20, None, D(6), D(0), D(0), D(6)),)
    assert result.accounting.leg_b.closed_unfilled_quantity == 5
    assert result.accounting.leg_b.acquired_quantity == 0


@pytest.mark.parametrize(("sale_order", "fill", "canceled"), [(0, 3, 2), (2, 0, 5)])
def test_tie_at_inclusive_cutoff(sale_order, fill, canceled):
    b = replace(
        _MIDDLE,
        arrivals=(replace(_SALE, order=sale_order),),
        cancellation=Cancellation(12, 8, completion_order=1),
    )
    result = _check_replay(replace(_SPEC, leg_b=b, cutoff_ms=20))
    assert result.trace[0].filled == result.accounting.leg_b.acquired_quantity == fill
    assert result.accounting.leg_b.closed_unfilled_quantity == canceled
    kinds = ["reject", "open", "request_cancel"]
    if fill:
        kinds.append("fill")
    assert [event.kind for event in result.events] == [*kinds, "complete_cancel"]


def test_fractional_queue_exhaustion_surplus_pending_full_fill_and_independent_legs():
    # Caller tuple order differs from chronological order and explicit tie order.
    arrivals = (
        SellArrival(12, D("1.5"), 9),
        SellArrival(11, D(".70")),
        SellArrival(9, D(".45")),
        SellArrival(12, D("1.25"), 2),
        SellArrival(15, D(1)),
    )
    a = replace(
        _OPEN,
        quantity=D(2),
        ahead_at_open=D("1.15"),
        arrivals=arrivals,
        cancellation=Cancellation(10, 4),
    )
    b = replace(_OPEN, ahead_at_open=D(0), arrivals=(SellArrival(12, D("1.75")),))
    result = _check_replay(QueueScenarioSpec(a, b, 15))
    assert [
        (r.time_ms, r.leg, r.order, r.consumed_ahead, r.filled, r.unused) for r in result.trace
    ] == [
        (9, "A", None, D(".45"), 0, 0),
        (11, "A", None, D(".70"), 0, 0),
        (12, "A", 2, 0, D("1.25"), 0),
        (12, "A", 9, 0, D(".75"), D(".75")),
        (12, "B", None, 0, D("1.75"), 0),
        (15, "A", None, 0, 0, 1),
    ]
    assert result.events == (
        ScenarioEvent("A", "open"),
        ScenarioEvent("B", "open"),
        ScenarioEvent("A", "request_cancel"),
        ScenarioEvent("A", "fill", D("1.25"), a.price_usd),
        ScenarioEvent("A", "fill", D(".75"), a.price_usd),
        ScenarioEvent("B", "fill", D("1.75"), b.price_usd),
    )
    assert result.accounting.leg_a.status == "filled"
    assert result.accounting.leg_b.open_quantity == D("3.25")


@pytest.mark.parametrize(
    ("cutoff", "status", "filled", "open_qty", "closed", "sales"),
    [
        (4, "awaiting_outcome", 0, 0, 0, 0),
        (5, "open", 0, 5, 0, 0),
        (19, "open", 0, 5, 0, 0),
        (20, "open", 3, 2, 0, 1),
        (24, "open", 3, 2, 0, 1),
        (25, "pending_cancel", 3, 2, 0, 1),
        (29, "pending_cancel", 3, 2, 0, 1),
        (30, "canceled", 3, 0, 2, 1),
    ],
)
def test_cutoff_snapshots_only_include_effective_events(
    cutoff, status, filled, open_qty, closed, sales
):
    result = _check_replay(replace(_SPEC, cutoff_ms=cutoff))
    b = result.accounting.leg_b
    assert (b.status, b.acquired_quantity, b.open_quantity, b.closed_unfilled_quantity) == (
        status,
        filled,
        open_qty,
        closed,
    )
    assert b.uncertainty == ()
    assert len(result.trace) == sales


def test_sales_around_opening_request_and_immediate_completion_at_one_time():
    b = replace(
        _OPEN,
        outcome_order=1,
        arrivals=tuple(SellArrival(5, D(4), i) for i in (6, 3, 0)),
        cancellation=Cancellation(5, 0, request_order=2, completion_order=4),
    )
    result = _check_replay(replace(_SPEC, leg_b=b, cutoff_ms=5))
    assert [(r.order, r.consumed_ahead, r.filled, r.unused) for r in result.trace] == [
        (0, 0, 0, 4),
        (3, 3, 1, 0),
        (6, 0, 0, 4),
    ]
    assert result.accounting.leg_b.closed_unfilled_quantity == 4


def test_rejected_leg_never_consumes_volume_and_submission_emits_no_event():
    a = replace(_REJECT, arrivals=(SellArrival(1, D(1)), SellArrival(3, D(2))))
    result = _check_replay(replace(_SPEC, leg_a=a, cutoff_ms=3))
    assert result.events == (ScenarioEvent("A", "reject"),)
    assert [r.unused for r in result.trace] == [1, 2]
    assert result.accounting.leg_a.closed_unfilled_quantity == 4
    assert result.accounting.leg_b.awaiting_outcome_quantity == 5
    assert _check_replay(replace(_SPEC, cutoff_ms=0)).events == ()


def test_public_accounting_returned_by_identity_and_pending_knowledge_supplied(monkeypatch):
    calls = []

    def observe(spec):
        actual = evaluate_scenario(spec)
        calls.append((spec, actual))
        return actual

    monkeypatch.setattr(simulation, "evaluate_scenario", observe)
    result = evaluate_queue_scenario(replace(_SPEC, cutoff_ms=25))
    ((accounting_input, actual),) = calls
    assert result.accounting is actual
    assert accounting_input.events == result.events
    assert accounting_input.leg_b_cutoff == CutoffKnowledge(True, True)
    assert accounting_input.payout_table == _SPEC.payout_table


def test_maximum_two_legs_emit_64_events_and_reject_thirtieth_arrival_even_after_cutoff():
    arrivals = tuple(SellArrival(i, D(".1")) for i in range(1, 30))
    leg = replace(
        _OPEN,
        submission_ms=0,
        processing_delay_ms=0,
        ahead_at_open=D(0),
        arrivals=arrivals,
        cancellation=Cancellation(30, 1),
    )
    spec = QueueScenarioSpec(leg, leg, 31)
    result = _check_replay(spec)
    assert len(result.trace) == 58
    assert len(result.events) == len(result.accounting.events) == 64
    assert result.accounting.gross_cost_usd == D("2.610")
    assert result.accounting.leg_b.closed_unfilled_quantity == D("2.1")
    for key in ("leg_a", "leg_b"):
        with pytest.raises(ScenarioValidationError, match="up to 29"):
            evaluate_queue_scenario(
                replace(spec, **{key: replace(leg, arrivals=(*arrivals, _SALE))}, cutoff_ms=0)
            )


@pytest.mark.parametrize(
    "b",
    [
        replace(_OPEN, arrivals=(SellArrival(5, D(0)),)),
        replace(_OPEN, outcome_order=0, arrivals=(SellArrival(5, D(1)),)),
        replace(_OPEN, arrivals=(SellArrival(7, D(1), 1), SellArrival(7, D(2), 1))),
        replace(_MIDDLE, cancellation=Cancellation(12, 8)),
        replace(_MIDDLE, cancellation=Cancellation(25, 0, request_order=0)),
        replace(_MIDDLE, cancellation=Cancellation(25, 0, request_order=2, completion_order=1)),
        replace(_OPEN, cancellation=Cancellation(4, 3)),
        replace(_OPEN, outcome_order=1, cancellation=Cancellation(5, 1, request_order=0)),
        replace(_REJECT, cancellation=Cancellation(4, 1)),
        replace(_MIDDLE, ahead_at_open=D(0)),
    ],
)
def test_unresolved_ties_and_impossible_histories_reject_entire_spec(b):
    for cutoff in (0, 31):
        with pytest.raises(ScenarioValidationError):
            evaluate_queue_scenario(replace(_SPEC, leg_b=b, cutoff_ms=cutoff))


@pytest.mark.parametrize(
    "value",
    [
        D("-0.00000001"),
        D("1e12"),
        D("0.000000001"),
        D("1.000000000"),
        D("NaN"),
        D("sNaN"),
        D("Infinity"),
        1,
        True,
        0.5,
        "1",
    ],
)
def test_decimal_rules_apply_to_every_queue_input_even_without_fills(value):
    for b in (
        replace(_OPEN, quantity=value),
        replace(_OPEN, price_usd=value),
        replace(_OPEN, ahead_at_open=value),
        replace(_OPEN, arrivals=(SellArrival(50, value),)),
    ):
        with pytest.raises(ScenarioValidationError):
            evaluate_queue_scenario(replace(_SPEC, leg_b=b, cutoff_ms=0))


@pytest.mark.parametrize("value", [-1, False, 1.0, D(1), "1"])
def test_times_delays_and_explicit_orders_require_nonnegative_exact_integers(value):
    for b in (
        replace(_OPEN, submission_ms=value),
        replace(_OPEN, processing_delay_ms=value),
        replace(_OPEN, outcome_order=value),
        replace(_OPEN, arrivals=(SellArrival(value, D(1)),)),
        replace(_OPEN, arrivals=(SellArrival(10, D(1), value),)),
        *(
            replace(_OPEN, cancellation=replace(Cancellation(10, 5), **{field: value}))
            for field in ("request_ms", "delay_ms", "request_order", "completion_order")
        ),
    ):
        with pytest.raises(ScenarioValidationError):
            evaluate_queue_scenario(replace(_SPEC, leg_b=b))
    with pytest.raises(ScenarioValidationError):
        evaluate_queue_scenario(replace(_SPEC, cutoff_ms=value))


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        object.__new__(QueueScenarioSpec),
        replace(_SPEC, leg_a=None),
        replace(_SPEC, leg_b=replace(_OPEN, quantity=D("-0"))),
        replace(_SPEC, leg_b=replace(_OPEN, ahead_at_open=None)),
        replace(_SPEC, leg_a=replace(_REJECT, ahead_at_open=D(1))),
        replace(_SPEC, leg_b=replace(_OPEN, outcome="pending")),
        replace(_SPEC, leg_b=replace(_OPEN, arrivals=[_SALE])),
        replace(_SPEC, leg_b=replace(_OPEN, arrivals=(object.__new__(SellArrival),))),
        replace(_SPEC, leg_b=replace(_OPEN, arrivals=(ScenarioEvent("B", "open"),))),
        replace(_SPEC, leg_b=replace(_OPEN, cancellation=(Cancellation(9, 1),))),
        replace(_SPEC, payout_table=list(_SPEC.payout_table)),
        replace(_SPEC, payout_table=_SPEC.payout_table * 17),
        replace(_SPEC, payout_table=(HypotheticalPayout("bad", D(-1), D(0)),)),
    ],
)
def test_malformed_or_uninitialized_inputs_rejected(invalid):
    with pytest.raises(ScenarioValidationError):
        evaluate_queue_scenario(invalid)


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
def test_exact_at_maximum_precision_and_preserves_caller_context_on_success_and_failure(rounding):
    maximum, unit = D("999999999999.99999999"), D(".00000001")
    leg = replace(
        _OPEN,
        quantity=maximum,
        price_usd=maximum,
        ahead_at_open=unit,
        arrivals=(SellArrival(10, maximum), SellArrival(11, unit), SellArrival(12, maximum)),
    )
    spec = QueueScenarioSpec(leg, leg, 12, (HypotheticalPayout("both", maximum, maximum),))
    expected = _check_replay(spec)
    assert expected.trace[0].consumed_ahead == unit
    assert expected.trace[0].filled == D("999999999999.99999998")
    assert expected.trace[2].filled == unit
    assert expected.trace[-1].unused == maximum
    assert expected.accounting.gross_cost_usd == D("1999999999999999999960000.0000000000000002")
    assert expected.accounting.payouts[0].gross_payout_usd == expected.accounting.gross_cost_usd
    with localcontext() as caller:
        caller.prec, caller.Emin, caller.Emax = 1, -1, 1
        caller.rounding, caller.clamp = rounding, 1
        for signal in caller.traps:
            caller.traps[signal] = True
        caller.flags[Inexact] = True
        before = repr(caller)
        for _ in range(2):
            assert evaluate_queue_scenario(spec) == expected
        with pytest.raises(ScenarioValidationError):
            evaluate_queue_scenario(replace(spec, leg_b=replace(leg, price_usd=D("sNaN"))))
        assert getcontext() is caller and repr(caller) == before


def test_zero_volume_and_price_with_extreme_zero_exponents():
    zero = D("0E+1000000")
    leg = replace(
        _OPEN,
        ahead_at_open=zero,
        price_usd=zero,
        arrivals=(SellArrival(8, zero), SellArrival(9, D("0.00000001"))),
    )
    result = _check_replay(replace(_SPEC, leg_b=leg))
    assert result.trace[0].volume.as_tuple() == zero.as_tuple()
    assert result.trace[1].filled == D("0.00000001")
    assert result.accounting.gross_cost_usd == 0


def test_deep_immutability_and_repeatability():
    result = _check_replay(_SPEC)
    for obj, field in [
        (_SPEC, "leg_a"),
        (_MIDDLE, "arrivals"),
        (_SALE, "order"),
        (_MIDDLE.cancellation, "delay_ms"),
        (result, "accounting"),
        (result.trace[0], "filled"),
        (result.events[-1], "kind"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, None)
        assert not hasattr(obj, "__dict__")
    assert type(result.trace) is type(result.events) is tuple
    assert evaluate_queue_scenario(_SPEC) == result
