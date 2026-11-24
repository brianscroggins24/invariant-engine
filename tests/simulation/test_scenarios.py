from decimal import Decimal

import pytest

from invariant_engine.simulation import (
    CutoffKnowledge,
    HypotheticalPayout,
    PayoutResult,
    ScenarioEvent,
    ScenarioSpec,
    evaluate_scenario,
)
from invariant_engine.simulation.models import Leg

_TEN = Decimal(10)
_COMPLETE = CutoffKnowledge(True)
_OPEN_A = ScenarioEvent("A", "open")
_OPEN_B = ScenarioEvent("B", "open")
_REJECT_A = ScenarioEvent("A", "reject")
_REJECT_B = ScenarioEvent("B", "reject")
_REQUEST_B = ScenarioEvent("B", "request_cancel")
_COMPLETE_B = ScenarioEvent("B", "complete_cancel")


def _example_fill(leg: Leg, quantity: int) -> ScenarioEvent:
    return ScenarioEvent(leg, "fill", Decimal(quantity), Decimal(".40" if leg == "A" else ".50"))


@pytest.mark.parametrize(
    ("events", "acquired", "open_", "closed_unfilled", "leg_costs", "gross_cost"),
    [
        pytest.param(
            (_OPEN_A, _OPEN_B, _example_fill("A", 10), _example_fill("B", 10)),
            (10, 10),
            (0, 0),
            (0, 0),
            ("4.00", "5.00"),
            "9.00",
            id="both-fill",
        ),
        pytest.param(
            (_OPEN_A, _OPEN_B),
            (0, 0),
            (10, 10),
            (0, 0),
            ("0.00", "0.00"),
            "0.00",
            id="both-open",
        ),
        pytest.param(
            (_OPEN_A, _REJECT_B, _example_fill("A", 10)),
            (10, 0),
            (0, 0),
            (0, 10),
            ("4.00", "0.00"),
            "4.00",
            id="a-fills-b-rejected",
        ),
        pytest.param(
            (_OPEN_B, _REJECT_A, _example_fill("B", 10)),
            (0, 10),
            (0, 0),
            (10, 0),
            ("0.00", "5.00"),
            "5.00",
            id="b-fills-a-rejected",
        ),
        pytest.param(
            (_OPEN_A, _OPEN_B, _example_fill("A", 6), _example_fill("B", 4)),
            (6, 4),
            (4, 6),
            (0, 0),
            ("2.40", "2.00"),
            "4.40",
            id="uneven-partials",
        ),
        pytest.param(
            (
                _OPEN_A,
                _OPEN_B,
                _example_fill("A", 10),
                _example_fill("B", 3),
                _REQUEST_B,
                _COMPLETE_B,
            ),
            (10, 3),
            (0, 0),
            (0, 7),
            ("4.00", "1.50"),
            "5.50",
            id="cancellation-completes",
        ),
        pytest.param(
            (
                _OPEN_A,
                _OPEN_B,
                _example_fill("A", 10),
                _example_fill("B", 3),
                _REQUEST_B,
                _example_fill("B", 2),
                _COMPLETE_B,
            ),
            (10, 5),
            (0, 0),
            (0, 5),
            ("4.00", "2.50"),
            "6.50",
            id="fill-while-pending",
        ),
    ],
)
def test_committed_acceptance_examples(
    events, acquired, open_, closed_unfilled, leg_costs, gross_cost
):
    result = evaluate_scenario(ScenarioSpec(_TEN, _TEN, events, _COMPLETE, _COMPLETE))
    assert result.conditional is True
    assert result.actionable is False
    assert result.payouts == ()
    assert tuple(snapshot.event for snapshot in result.events) == events
    assert tuple(snapshot.event_index for snapshot in result.events) == tuple(range(len(events)))
    assert result.gross_cost_usd == result.confirmed_gross_cost_usd == Decimal(gross_cost)
    for i, cutoff in enumerate((result.leg_a, result.leg_b)):
        assert cutoff.intended_quantity == _TEN
        assert cutoff.awaiting_outcome_quantity == 0
        assert cutoff.acquired_quantity == cutoff.confirmed_acquired_quantity == acquired[i]
        assert cutoff.open_quantity == open_[i]
        assert cutoff.closed_unfilled_quantity == closed_unfilled[i]
        assert cutoff.gross_cost_usd == cutoff.confirmed_gross_cost_usd == Decimal(leg_costs[i])
        assert cutoff.uncertainty == ()
    for snapshot in result.events:
        a, b = snapshot.leg_a, snapshot.leg_b
        assert snapshot.gross_cost_usd == a.gross_cost_usd + b.gross_cost_usd
        for state in (a, b):
            assert _TEN == (
                state.acquired_quantity
                + state.open_quantity
                + state.closed_unfilled_quantity
                + state.awaiting_outcome_quantity
            )


def test_fractional_fills_use_separate_supplied_prices_and_preserve_interleaving():
    events = (
        _OPEN_B,
        ScenarioEvent("B", "fill", Decimal("0.125"), Decimal("0.12")),
        _OPEN_A,
        ScenarioEvent("B", "fill", Decimal("0.375"), Decimal("0.34")),
        ScenarioEvent("A", "fill", Decimal("0.30"), Decimal("0.10")),
    )
    result = evaluate_scenario(ScenarioSpec(_TEN, _TEN, events, _COMPLETE, _COMPLETE))
    assert tuple(snapshot.fill_cost_usd for snapshot in result.events) == (
        None,
        Decimal("0.015"),
        None,
        Decimal("0.1275"),
        Decimal("0.0300"),
    )
    assert result.events[1].leg_a.awaiting_outcome_quantity == _TEN
    assert result.events[1].leg_b.acquired_quantity == Decimal("0.125")
    assert result.events[3].leg_a.status == "open"
    assert result.leg_b.acquired_quantity == Decimal("0.500")
    assert result.leg_b.open_quantity == Decimal("9.500")
    assert result.leg_b.gross_cost_usd == Decimal("0.1425")
    assert result.gross_cost_usd == Decimal("0.1725")


def test_full_fill_closes_pending_cancellation_and_fixes_cutoff_totals():
    events = (_OPEN_B, _example_fill("B", 2), _REQUEST_B, _example_fill("B", 8))
    result = evaluate_scenario(
        ScenarioSpec(_TEN, _TEN, events, _COMPLETE, CutoffKnowledge(False, False))
    )
    assert result.events[2].leg_b.status == "pending_cancel"
    assert result.events[2].leg_b.open_quantity == 8
    assert result.events[3].leg_b.status == result.leg_b.status == "filled"
    assert result.leg_b.closed_unfilled_quantity == result.leg_b.open_quantity == 0
    assert result.leg_b.acquired_quantity == _TEN
    assert result.gross_cost_usd == Decimal("5.00")
    assert result.leg_b.uncertainty == ()


@pytest.mark.parametrize("fills_complete", [True, False])
def test_initial_and_rejected_legs_cannot_receive_unsupplied_fills(fills_complete):
    knowledge = CutoffKnowledge(fills_complete)
    result = evaluate_scenario(ScenarioSpec(_TEN, _TEN, (_REJECT_A,), knowledge, knowledge))
    assert result.leg_a.status == "rejected"
    assert result.leg_a.closed_unfilled_quantity == _TEN
    assert result.leg_b.status == "awaiting_outcome"
    assert result.leg_b.awaiting_outcome_quantity == _TEN
    assert result.leg_a.acquired_quantity == result.leg_b.acquired_quantity == 0
    assert result.gross_cost_usd == 0


@pytest.mark.parametrize(
    ("suffix", "completion_known", "status", "open_", "closed", "reasons"),
    [
        ((), None, None, None, 0, ("incomplete_fills",)),
        ((_REQUEST_B,), True, None, None, 0, ("incomplete_fills",)),
        (
            (_REQUEST_B,),
            False,
            None,
            None,
            None,
            ("incomplete_fills", "unknown_cancellation_completion"),
        ),
        ((_REQUEST_B, _COMPLETE_B), None, "canceled", 0, None, ("incomplete_fills",)),
    ],
)
def test_incomplete_fills_only_hide_affected_cutoff_values(
    suffix, completion_known, status, open_, closed, reasons
):
    events = (_OPEN_A, _OPEN_B, _example_fill("B", 3), _example_fill("A", 2), *suffix)
    result = evaluate_scenario(
        ScenarioSpec(_TEN, _TEN, events, _COMPLETE, CutoffKnowledge(False, completion_known))
    )
    assert result.leg_a.acquired_quantity == 2
    assert result.leg_a.gross_cost_usd == Decimal("0.80")
    assert (
        result.leg_b.confirmed_acquired_quantity == result.events[-1].leg_b.acquired_quantity == 3
    )
    assert result.leg_b.confirmed_gross_cost_usd == Decimal("1.50")
    assert result.leg_b.acquired_quantity is result.leg_b.gross_cost_usd is None
    assert result.leg_b.status == status
    assert result.leg_b.open_quantity == open_
    assert result.leg_b.closed_unfilled_quantity == closed
    assert result.leg_b.awaiting_outcome_quantity == 0
    assert result.leg_b.uncertainty == reasons
    assert result.confirmed_gross_cost_usd == Decimal("2.30")
    assert result.gross_cost_usd is None


@pytest.mark.parametrize("leg", ["A", "B"])
@pytest.mark.parametrize("earlier_fill", [False, True])
@pytest.mark.parametrize(
    ("remainder", "completed", "exact"),
    [
        pytest.param("0.00000001", True, True, id="completed-minimum"),
        pytest.param("0.00000002", True, False, id="completed-two-increments"),
        pytest.param("0.00000001", False, False, id="pending-minimum"),
    ],
)
def test_cancellation_bounds_unreported_fills_at_minimum_quantity(
    leg, earlier_fill, remainder, completed, exact
):
    acquired = Decimal(int(earlier_fill))
    quantity = acquired + Decimal(remainder)
    price = Decimal("0.40")
    events = [ScenarioEvent(leg, "open")]
    if earlier_fill:
        events.append(ScenarioEvent(leg, "fill", acquired, price))
    events.append(ScenarioEvent(leg, "request_cancel"))
    if completed:
        events.append(ScenarioEvent(leg, "complete_cancel"))

    knowledge = CutoffKnowledge(False, None if completed else True)
    knowledge_a, knowledge_b = (knowledge, _COMPLETE) if leg == "A" else (_COMPLETE, knowledge)
    table = (HypotheticalPayout("one-dollar-per-unit", Decimal(1), Decimal(1)),)
    result = evaluate_scenario(
        ScenarioSpec(quantity, quantity, tuple(events), knowledge_a, knowledge_b, table)
    )
    cutoff = result.leg_a if leg == "A" else result.leg_b
    assert cutoff.confirmed_acquired_quantity == acquired
    assert cutoff.confirmed_gross_cost_usd == result.confirmed_gross_cost_usd == acquired * price
    assert cutoff.status == ("canceled" if completed else None)
    assert cutoff.open_quantity == (0 if completed else None)

    payout = result.payouts[0]
    leg_payout = payout.leg_a_payout_usd if leg == "A" else payout.leg_b_payout_usd
    if exact:
        assert cutoff.acquired_quantity == acquired
        assert cutoff.closed_unfilled_quantity == Decimal(remainder)
        assert cutoff.gross_cost_usd == result.gross_cost_usd == acquired * price
        assert leg_payout == payout.gross_payout_usd == acquired
        assert cutoff.uncertainty == ()
    else:
        assert cutoff.acquired_quantity is cutoff.gross_cost_usd is result.gross_cost_usd is None
        assert cutoff.closed_unfilled_quantity == (None if completed else 0)
        assert leg_payout is payout.gross_payout_usd is None
        assert cutoff.uncertainty == ("incomplete_fills",)


@pytest.mark.parametrize("completion_known", [True, False])
def test_cancellation_completion_knowledge_does_not_change_confirmed_fill_totals(completion_known):
    events = (_OPEN_B, _example_fill("B", 3), _REQUEST_B)
    result = evaluate_scenario(
        ScenarioSpec(_TEN, _TEN, events, _COMPLETE, CutoffKnowledge(True, completion_known))
    )
    assert result.leg_b.acquired_quantity == 3
    assert result.leg_b.gross_cost_usd == result.gross_cost_usd == Decimal("1.50")
    assert result.leg_b.supplied_state.open_quantity == 7
    if completion_known:
        assert result.leg_b.status == "pending_cancel"
        assert result.leg_b.open_quantity == 7
        assert result.leg_b.closed_unfilled_quantity == 0
        assert result.leg_b.uncertainty == ()
    else:
        assert result.leg_b.status is None
        assert result.leg_b.open_quantity is result.leg_b.closed_unfilled_quantity is None
        assert result.leg_b.uncertainty == ("unknown_cancellation_completion",)


def test_hypothetical_payouts_preserve_order_and_exact_amounts_including_zero():
    table = (
        HypotheticalPayout("both", Decimal("0.22"), Decimal("0.42")),
        HypotheticalPayout("only-b", Decimal(0), Decimal("1.25")),
        HypotheticalPayout("only-a", Decimal("0.40"), Decimal(0)),
    )
    events = (
        _OPEN_B,
        _OPEN_A,
        ScenarioEvent("A", "fill", Decimal("0.125"), Decimal("0.50")),
        ScenarioEvent("B", "fill", Decimal("0.75"), Decimal("0.50")),
        _REQUEST_B,
    )
    spec = ScenarioSpec(_TEN, _TEN, events, _COMPLETE, CutoffKnowledge(True, False), table)
    assert evaluate_scenario(spec).payouts == (
        PayoutResult("both", Decimal("0.02750"), Decimal("0.3150"), Decimal("0.34250")),
        PayoutResult("only-b", Decimal(0), Decimal("0.9375"), Decimal("0.9375")),
        PayoutResult("only-a", Decimal("0.05000"), Decimal(0), Decimal("0.05000")),
    )
    incomplete = ScenarioSpec(_TEN, _TEN, events, _COMPLETE, CutoffKnowledge(False, True), table)
    assert evaluate_scenario(incomplete).payouts == (
        PayoutResult("both", Decimal("0.02750"), None, None),
        PayoutResult("only-b", Decimal(0), None, None),
        PayoutResult("only-a", Decimal("0.05000"), Decimal(0), Decimal("0.05000")),
    )
