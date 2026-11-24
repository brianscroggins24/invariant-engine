from dataclasses import FrozenInstanceError, replace
from decimal import ROUND_DOWN, Decimal, Inexact, Overflow, Rounded, getcontext, localcontext

import pytest

from invariant_engine.simulation import (
    CutoffKnowledge,
    HypotheticalPayout,
    ScenarioEvent,
    ScenarioSpec,
    ScenarioValidationError,
    evaluate_scenario,
)

_OPEN = ScenarioEvent("A", "open")
_REJECT = ScenarioEvent("A", "reject")
_FILL = ScenarioEvent("A", "fill", Decimal(1), Decimal("0.40"))
_FULL_FILL = replace(_FILL, quantity=Decimal(10))
_REQUEST = ScenarioEvent("A", "request_cancel")
_COMPLETION = ScenarioEvent("A", "complete_cancel")
_ROW = HypotheticalPayout("state", Decimal(1), Decimal(0))
_BASIC = ScenarioSpec(Decimal(10), Decimal(10), (), CutoffKnowledge(True), CutoffKnowledge(True))


@pytest.mark.parametrize(
    "events",
    [
        (_FILL,),
        (_REQUEST,),
        (_COMPLETION,),
        (_OPEN, _OPEN),
        (_OPEN, _REJECT),
        (_OPEN, _COMPLETION),
        (_OPEN, _FULL_FILL, _FILL),
        (_OPEN, _REQUEST, _REQUEST),
        (_OPEN, _REQUEST, _FULL_FILL, _COMPLETION),
        (_OPEN, _REQUEST, _COMPLETION, _FILL),
        (_OPEN, _REQUEST, _COMPLETION, _COMPLETION),
        (_REJECT, _OPEN),
        (_REJECT, _REJECT),
        (_REJECT, _FILL),
        (_OPEN, _FILL, replace(_FULL_FILL, quantity=Decimal("9.00000001"))),
    ],
)
def test_invalid_transition_rejects_whole_scenario_with_deterministic_error(events):
    spec = replace(_BASIC, events=events)
    messages = []
    for _ in range(2):
        with pytest.raises(
            ScenarioValidationError, match=rf"^events\[{len(events) - 1}\]"
        ) as error:
            evaluate_scenario(spec)
        messages.append(str(error.value))
    assert messages[0] == messages[1]


def test_pending_cutoff_requires_explicit_cancellation_completion_knowledge():
    spec = replace(_BASIC, events=(_OPEN, _REQUEST))
    with pytest.raises(ScenarioValidationError, match="leg A requires explicit cancellation"):
        evaluate_scenario(spec)


@pytest.mark.parametrize(
    "number",
    [
        1,
        True,
        0.4,
        "1",
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("1000000000000"),
        Decimal("1E+1000000"),
        Decimal("0.000000001"),
        Decimal("0.400000000"),
    ],
)
def test_numeric_rules_apply_to_every_nested_number(number):
    for spec in (
        replace(_BASIC, leg_a_quantity=number),
        replace(_BASIC, leg_b_quantity=number),
        replace(_BASIC, events=(_OPEN, replace(_FILL, quantity=number))),
        replace(_BASIC, events=(_OPEN, replace(_FILL, price_usd=number))),
        replace(_BASIC, payout_table=(replace(_ROW, leg_a_usd_per_unit=number),)),
        replace(_BASIC, payout_table=(replace(_ROW, leg_b_usd_per_unit=number),)),
    ):
        with pytest.raises(ScenarioValidationError):
            evaluate_scenario(spec)


def test_positive_quantities_and_zero_price_and_payout():
    for spec in (
        replace(_BASIC, leg_b_quantity=Decimal(0)),
        replace(_BASIC, events=(_OPEN, replace(_FILL, quantity=Decimal("-0")))),
    ):
        with pytest.raises(ScenarioValidationError, match="must be positive"):
            evaluate_scenario(spec)
    spec = replace(
        _BASIC,
        events=(_OPEN, replace(_FILL, price_usd=Decimal("0E+1000000"))),
        payout_table=(replace(_ROW, leg_a_usd_per_unit=Decimal("0.00000000")),),
    )
    result = evaluate_scenario(spec)
    assert result.leg_a.acquired_quantity == 1
    assert result.events[1].event.price_usd.as_tuple() == Decimal("0E+1000000").as_tuple()
    assert result.gross_cost_usd == result.payouts[0].gross_payout_usd == 0


def test_event_and_payout_limits_are_inclusive_and_empty_history_is_valid():
    events = (_OPEN,) + (replace(_FILL, quantity=Decimal("0.00000001")),) * 63
    table = tuple(replace(_ROW, name=str(i)) for i in range(16))
    accepted = evaluate_scenario(replace(_BASIC, events=events, payout_table=table))
    assert len(accepted.events) == 64
    assert accepted.leg_a.acquired_quantity == Decimal("0.00000063")
    assert tuple(payout.name for payout in accepted.payouts) == tuple(row.name for row in table)
    assert evaluate_scenario(_BASIC).events == ()
    for spec, message in (
        (replace(_BASIC, events=(*events, _FILL)), "up to 64 events"),
        (replace(_BASIC, payout_table=(*table, _ROW)), "up to 16 states"),
        (replace(_BASIC, payout_table=(_ROW, _ROW)), "duplicates a state name"),
    ):
        with pytest.raises(ScenarioValidationError, match=message):
            evaluate_scenario(spec)


def test_deep_type_validation_rejects_mutable_nested_values_subclasses_and_missing_fields():
    class EventSubclass(ScenarioEvent):
        pass

    class SpecSubclass(ScenarioSpec):
        pass

    class TupleSubclass(tuple):
        pass

    class StringSubclass(str):
        pass

    class DecimalSubclass(Decimal):
        pass

    for malformed in (
        {},
        object.__new__(ScenarioSpec),
        SpecSubclass(Decimal(10), Decimal(10), (), CutoffKnowledge(True), CutoffKnowledge(True)),
        replace(_BASIC, leg_a_quantity=DecimalSubclass("10")),
        replace(_BASIC, events=[_OPEN]),
        replace(_BASIC, events=TupleSubclass([_OPEN])),
        replace(_BASIC, events=([],)),
        replace(_BASIC, events=(object.__new__(ScenarioEvent),)),
        replace(_BASIC, events=(EventSubclass("A", "open"),)),
        replace(_BASIC, events=(replace(_OPEN, leg="C"),)),
        replace(_BASIC, events=(replace(_OPEN, leg=StringSubclass("A")),)),
        replace(_BASIC, events=(replace(_OPEN, kind="sell"),)),
        replace(_BASIC, events=(replace(_OPEN, quantity=Decimal(0)),)),
        replace(_BASIC, events=(_OPEN, replace(_FILL, price_usd=None))),
        replace(_BASIC, events=(_OPEN, replace(_FILL, quantity=None))),
        replace(_BASIC, leg_b_cutoff={"fills_complete": True}),
        replace(_BASIC, leg_b_cutoff=CutoffKnowledge(1)),
        replace(_BASIC, leg_b_cutoff=CutoffKnowledge(True, 1)),
        replace(_BASIC, payout_table=[_ROW]),
        replace(_BASIC, payout_table=({"name": "state"},)),
        replace(_BASIC, payout_table=(replace(_ROW, name=""),)),
        replace(_BASIC, payout_table=(replace(_ROW, name=StringSubclass("state")),)),
    ):
        with pytest.raises(ScenarioValidationError):
            evaluate_scenario(malformed)


def test_accepted_records_are_nested_immutable_and_snapshots_have_no_input_alias():
    fill = replace(_FILL)
    spec = replace(_BASIC, events=(_OPEN, fill), payout_table=(_ROW,))
    result = evaluate_scenario(spec)
    for record, field in (
        (spec, "events"),
        (spec.leg_a_cutoff, "fills_complete"),
        (spec.events[-1], "quantity"),
        (spec.payout_table[0], "name"),
        (result, "actionable"),
        (result.events[0], "event_index"),
        (result.events[-1].event, "quantity"),
        (result.events[-1].leg_a, "status"),
        (result.leg_a, "acquired_quantity"),
        (result.leg_a.supplied_state, "status"),
        (result.payouts[0], "name"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, None)
        assert not hasattr(record, "__dict__")
    for collection in (
        spec.events,
        spec.payout_table,
        result.events,
        result.leg_a.uncertainty,
        result.payouts,
    ):
        assert type(collection) is tuple
    object.__setattr__(fill, "quantity", [])
    assert result.events[-1].event.quantity == Decimal(1)
    with pytest.raises(ScenarioValidationError, match=r"events\[1\] quantity"):
        evaluate_scenario(spec)


def test_exact_arithmetic_at_input_limits_with_hostile_decimal_context():
    maximum = Decimal("999999999999.99999999")
    events = (
        _OPEN,
        ScenarioEvent("B", "open"),
        ScenarioEvent("A", "fill", maximum, maximum),
        ScenarioEvent("B", "fill", maximum, maximum),
    )
    spec = replace(
        _BASIC,
        leg_a_quantity=maximum,
        leg_b_quantity=maximum,
        events=events,
        payout_table=(HypotheticalPayout("both", maximum, maximum),),
    )
    expected = evaluate_scenario(spec)
    with localcontext() as caller:
        caller.prec = 2
        caller.Emin = -2
        caller.Emax = 2
        caller.rounding = ROUND_DOWN
        caller.clamp = 1
        caller.traps[Inexact] = caller.traps[Rounded] = caller.traps[Overflow] = True
        caller.flags[Inexact] = True
        before = repr(caller)
        assert evaluate_scenario(spec) == expected
        with pytest.raises(ScenarioValidationError):
            evaluate_scenario(replace(spec, leg_a_quantity=Decimal("sNaN")))
        assert getcontext() is caller
        assert repr(caller) == before

    assert expected.events[-1].fill_cost_usd == Decimal("999999999999999999980000.0000000000000001")
    assert expected.gross_cost_usd == Decimal("1999999999999999999960000.0000000000000002")
    assert expected.payouts[0].gross_payout_usd == expected.gross_cost_usd
