"""Validate and account for a bounded, caller-supplied synthetic history."""

from dataclasses import replace
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)

from .models import (
    CutoffKnowledge,
    CutoffLegResult,
    EventResult,
    HypotheticalPayout,
    LegState,
    PayoutResult,
    ScenarioEvent,
    ScenarioResult,
    ScenarioSpec,
    ScenarioValidationError,
    Uncertainty,
)

_ZERO = Decimal(0)
_MAX_FRACTIONAL_DIGITS = 8
_MIN_FILL_QUANTITY = Decimal(f"1e-{_MAX_FRACTIONAL_DIGITS}")


def evaluate_scenario(spec: ScenarioSpec) -> ScenarioResult:
    """Return conditional, non-actionable accounting or raise ScenarioValidationError."""
    if type(spec) is not ScenarioSpec:
        raise ScenarioValidationError("expected a ScenarioSpec")

    # Products have up to 24 integer and 16 fractional digits. Even a sum of
    # 64 such products fits in 42 digits. Specify every context setting to
    # remain independent of both the caller's context and Decimal's DefaultContext.
    with localcontext(
        Context(
            prec=42,
            Emin=-16,
            Emax=25,
            rounding=ROUND_HALF_EVEN,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[Inexact, Rounded, InvalidOperation, Overflow],
        )
    ):
        try:
            return _evaluate(spec)
        except AttributeError:
            raise ScenarioValidationError("scenario has an uninitialized field") from None


def _evaluate(spec: ScenarioSpec) -> ScenarioResult:
    leg_a = _initial_state(_decimal(spec.leg_a_quantity, "leg A quantity", positive=True))
    leg_b = _initial_state(_decimal(spec.leg_b_quantity, "leg B quantity", positive=True))
    _check_knowledge(spec.leg_a_cutoff, "A")
    _check_knowledge(spec.leg_b_cutoff, "B")
    if type(spec.events) is not tuple or len(spec.events) > 64:
        raise ScenarioValidationError("events must be a tuple of up to 64 events")
    payout_table = _validate_payout_table(spec.payout_table)

    event_results = []
    for index, supplied_event in enumerate(spec.events):
        event = _validate_event(supplied_event, index)
        state = leg_a if event.leg == "A" else leg_b
        state, fill_cost = _apply_event(state, event, index)
        if event.leg == "A":
            leg_a = state
        else:
            leg_b = state
        event_results.append(
            EventResult(
                index, event, leg_a, leg_b, fill_cost, leg_a.gross_cost_usd + leg_b.gross_cost_usd
            )
        )

    cutoff_a = _at_cutoff(leg_a, spec.leg_a_cutoff, "A")
    cutoff_b = _at_cutoff(leg_b, spec.leg_b_cutoff, "B")
    return ScenarioResult(
        events=tuple(event_results),
        leg_a=cutoff_a,
        leg_b=cutoff_b,
        confirmed_gross_cost_usd=leg_a.gross_cost_usd + leg_b.gross_cost_usd,
        gross_cost_usd=_known_sum(cutoff_a.gross_cost_usd, cutoff_b.gross_cost_usd),
        payouts=tuple(_payout(row, cutoff_a, cutoff_b) for row in payout_table),
    )


def _decimal(value: object, label: str, *, positive: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value < _ZERO:
        raise ScenarioValidationError(f"{label} must be a finite nonnegative Decimal")
    if positive and value.is_zero():
        raise ScenarioValidationError(f"{label} must be positive")
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)  # Finiteness was checked above.
    if exponent < -_MAX_FRACTIONAL_DIGITS or (not value.is_zero() and value.adjusted() >= 12):
        raise ScenarioValidationError(
            f"{label} exceeds 12 integer or {_MAX_FRACTIONAL_DIGITS} fractional digits"
        )
    return value


def _check_knowledge(knowledge: CutoffKnowledge, leg: str) -> None:
    if type(knowledge) is not CutoffKnowledge or type(knowledge.fills_complete) is not bool:
        raise ScenarioValidationError(f"leg {leg} requires explicit Boolean fill completeness")
    completion = knowledge.cancellation_completion_known
    if completion is not None and type(completion) is not bool:
        raise ScenarioValidationError(f"leg {leg} has invalid cancellation completion knowledge")


def _validate_payout_table(table: tuple[HypotheticalPayout, ...]) -> tuple[HypotheticalPayout, ...]:
    if type(table) is not tuple or len(table) > 16:
        raise ScenarioValidationError("payout_table must be a tuple of up to 16 states")
    names: set[str] = set()
    rows = []
    for index, row in enumerate(table):
        label = f"payout_table[{index}]"
        if type(row) is not HypotheticalPayout or type(row.name) is not str or not row.name:
            raise ScenarioValidationError(f"{label} requires a nonempty state name")
        if row.name in names:
            raise ScenarioValidationError(f"{label} duplicates a state name")
        names.add(row.name)
        rows.append(
            HypotheticalPayout(
                row.name,
                _decimal(row.leg_a_usd_per_unit, f"{label} leg A payout"),
                _decimal(row.leg_b_usd_per_unit, f"{label} leg B payout"),
            )
        )
    return tuple(rows)


def _validate_event(event: ScenarioEvent, index: int) -> ScenarioEvent:
    label = f"events[{index}]"
    if (
        type(event) is not ScenarioEvent
        or type(event.leg) is not str
        or event.leg not in ("A", "B")
    ):
        raise ScenarioValidationError(f"{label} requires a scenario event for leg A or B")
    if type(event.kind) is not str or event.kind not in (
        "open",
        "reject",
        "fill",
        "request_cancel",
        "complete_cancel",
    ):
        raise ScenarioValidationError(f"{label} has an unsupported event kind")
    if event.kind == "fill":
        return ScenarioEvent(
            event.leg,
            event.kind,
            _decimal(event.quantity, f"{label} quantity", positive=True),
            _decimal(event.price_usd, f"{label} USD price"),
        )
    if event.quantity is not None or event.price_usd is not None:
        raise ScenarioValidationError(f"{label} carries fill fields on a non-fill event")
    return ScenarioEvent(event.leg, event.kind)


def _initial_state(quantity: Decimal) -> LegState:
    return LegState(quantity, "awaiting_outcome", _ZERO, _ZERO, _ZERO, quantity, _ZERO)


def _apply_event(
    state: LegState, event: ScenarioEvent, index: int
) -> tuple[LegState, Decimal | None]:
    match event.kind, state.status:
        case "open", "awaiting_outcome":
            return replace(
                state,
                status="open",
                open_quantity=state.intended_quantity,
                awaiting_outcome_quantity=_ZERO,
            ), None
        case "reject", "awaiting_outcome":
            return replace(
                state,
                status="rejected",
                closed_unfilled_quantity=state.intended_quantity,
                awaiting_outcome_quantity=_ZERO,
            ), None
        case "request_cancel", "open":
            return replace(state, status="pending_cancel"), None
        case "complete_cancel", "pending_cancel":
            return replace(
                state,
                status="canceled",
                open_quantity=_ZERO,
                closed_unfilled_quantity=state.open_quantity,
            ), None
        case "fill", ("open" | "pending_cancel"):
            quantity, price = event.quantity, event.price_usd
            assert quantity is not None and price is not None  # Validated fill payload.
            if quantity > state.open_quantity:
                raise ScenarioValidationError(f"events[{index}] fill exceeds the open quantity")
            open_quantity = state.open_quantity - quantity
            # Zero can carry an arbitrarily large positive Decimal exponent.
            cost = _ZERO if price.is_zero() else quantity * price
            return replace(
                state,
                status="filled" if open_quantity.is_zero() else state.status,
                acquired_quantity=state.acquired_quantity + quantity,
                open_quantity=open_quantity,
                gross_cost_usd=state.gross_cost_usd + cost,
            ), cost
        case _:
            raise ScenarioValidationError(
                f"events[{index}] {event.kind} is invalid for leg {event.leg} "
                f"in state {state.status}"
            )


def _at_cutoff(state: LegState, knowledge: CutoffKnowledge, leg: str) -> CutoffLegResult:
    pending = state.status == "pending_cancel"
    if pending and knowledge.cancellation_completion_known is None:
        raise ScenarioValidationError(
            f"leg {leg} requires explicit cancellation completion knowledge"
        )

    canceled = state.status == "canceled"
    # A completed cancellation requires a positive remainder. At the minimum
    # increment, any additional fill would have closed the leg as filled.
    fills_unknown = not knowledge.fills_complete and (
        state.status in ("open", "pending_cancel")
        or (canceled and state.closed_unfilled_quantity > _MIN_FILL_QUANTITY)
    )
    cancellation_unknown = pending and knowledge.cancellation_completion_known is False
    uncertainty: list[Uncertainty] = []
    if fills_unknown:
        uncertainty.append("incomplete_fills")
    if cancellation_unknown:
        uncertainty.append("unknown_cancellation_completion")

    # Confirmed completion fixes open at zero even if pre-completion fills are missing.
    open_unknown = cancellation_unknown or (fills_unknown and not canceled)
    closed_unknown = cancellation_unknown or (fills_unknown and canceled)
    return CutoffLegResult(
        supplied_state=state,
        status=None if open_unknown else state.status,
        acquired_quantity=None if fills_unknown else state.acquired_quantity,
        open_quantity=None if open_unknown else state.open_quantity,
        closed_unfilled_quantity=None if closed_unknown else state.closed_unfilled_quantity,
        gross_cost_usd=None if fills_unknown else state.gross_cost_usd,
        uncertainty=tuple(uncertainty),
    )


def _known_sum(first: Decimal | None, second: Decimal | None) -> Decimal | None:
    return None if first is None or second is None else first + second


def _position_payout(quantity: Decimal | None, usd_per_unit: Decimal) -> Decimal | None:
    if usd_per_unit.is_zero():
        return _ZERO
    return None if quantity is None else quantity * usd_per_unit


def _payout(
    row: HypotheticalPayout, leg_a: CutoffLegResult, leg_b: CutoffLegResult
) -> PayoutResult:
    payout_a = _position_payout(leg_a.acquired_quantity, row.leg_a_usd_per_unit)
    payout_b = _position_payout(leg_b.acquired_quantity, row.leg_b_usd_per_unit)
    return PayoutResult(row.name, payout_a, payout_b, _known_sum(payout_a, payout_b))
