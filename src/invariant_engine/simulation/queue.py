"""Match synthetic sell arrivals and replay the resulting two-leg buy history."""

from dataclasses import dataclass
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
from itertools import pairwise
from typing import Literal

from invariant_engine import simulation
from invariant_engine.simulation import (
    CutoffKnowledge,
    ScenarioEvent,
    ScenarioSpec,
    ScenarioValidationError,
)

from .queue_models import (
    ArrivalTrace,
    Cancellation,
    QueueLegSpec,
    QueueScenarioResult,
    QueueScenarioSpec,
    SellArrival,
)

_Leg = Literal["A", "B"]
_Kind = Literal["open", "reject", "sell", "request_cancel", "complete_cancel"]
_ZERO = Decimal(0)


def _nonnegative_int(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ScenarioValidationError(f"{label} must be a nonnegative integer")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value < _ZERO:
        raise ScenarioValidationError(f"{label} must be a finite nonnegative Decimal")
    exponent = value.as_tuple().exponent
    assert isinstance(exponent, int)
    if exponent < -8 or (not value.is_zero() and value.adjusted() >= 12):
        raise ScenarioValidationError(f"{label} exceeds 12 integer or 8 fractional digits")
    return value


@dataclass(frozen=True, slots=True)
class _Scheduled:
    leg: _Leg
    time_ms: int
    order: int | None
    kind: _Kind
    volume: Decimal = _ZERO

    def sort_key(self) -> tuple[int, _Leg, int]:
        return self.time_ms, self.leg, -1 if self.order is None else self.order


def _schedule(leg: _Leg, spec: QueueLegSpec) -> list[_Scheduled]:
    if type(spec) is not QueueLegSpec:
        raise ScenarioValidationError(f"leg {leg} requires a QueueLegSpec")
    if _decimal(spec.quantity, "intended quantity").is_zero():
        raise ScenarioValidationError("intended quantity must be positive")
    _decimal(spec.price_usd, "USD price")
    if type(spec.outcome) is not str or spec.outcome not in ("open", "reject"):
        raise ScenarioValidationError("processing outcome must be open or reject")
    if spec.outcome == "open":
        _decimal(spec.ahead_at_open, "queue ahead at opening")
    elif spec.ahead_at_open is not None:
        raise ScenarioValidationError("a rejected leg cannot have a queue at opening")

    outcome_ms = _nonnegative_int(spec.submission_ms, "submission time") + _nonnegative_int(
        spec.processing_delay_ms, "processing delay"
    )
    scheduled = [_Scheduled(leg, outcome_ms, spec.outcome_order, spec.outcome)]
    if type(spec.arrivals) is not tuple or len(spec.arrivals) > 29:
        raise ScenarioValidationError("arrivals must be a tuple of up to 29 sell arrivals per leg")
    for arrival in spec.arrivals:
        if type(arrival) is not SellArrival:
            raise ScenarioValidationError("expected a SellArrival")
        time_ms = _nonnegative_int(arrival.time_ms, "arrival time")
        volume = _decimal(arrival.volume, "sell volume")
        scheduled.append(_Scheduled(leg, time_ms, arrival.order, "sell", volume))

    cancel = spec.cancellation
    if cancel is not None:
        if type(cancel) is not Cancellation:
            raise ScenarioValidationError("expected one Cancellation")
        request = _nonnegative_int(cancel.request_ms, "request time")
        completion = request + _nonnegative_int(cancel.delay_ms, "cancellation delay")
        scheduled.append(_Scheduled(leg, request, cancel.request_order, "request_cancel"))
        scheduled.append(_Scheduled(leg, completion, cancel.completion_order, "complete_cancel"))
    for event in scheduled:
        if event.order is not None:
            _nonnegative_int(event.order, "tie order")
    return scheduled


@dataclass(slots=True)
class _Queue:
    remaining: Decimal
    ahead: Decimal = _ZERO
    status: Literal["awaiting_outcome", "open", "pending_cancel", "filled", "closed"] = (
        "awaiting_outcome"
    )

    def sell(self, event: _Scheduled) -> ArrivalTrace:
        ahead = filled = _ZERO
        unused = event.volume
        if self.status in ("open", "pending_cancel"):
            ahead = min(unused, self.ahead)
            self.ahead -= ahead
            unused -= ahead
            filled = min(unused, self.remaining)
            self.remaining -= filled
            unused -= filled
            if self.remaining.is_zero():
                self.status = "filled"
        return ArrivalTrace(
            event.leg, event.time_ms, event.order, event.volume, ahead, filled, unused
        )

    def transition(self, event: _Scheduled, spec: QueueLegSpec) -> ScenarioEvent | None:
        match event.kind:
            case "open":
                assert spec.ahead_at_open is not None
                self.ahead = spec.ahead_at_open
                self.status = "open"
            case "reject":
                self.status = "closed"
            case "request_cancel":
                if self.status != "open":
                    raise ScenarioValidationError(
                        f"leg {event.leg} cancellation requires an open leg"
                    )
                self.status = "pending_cancel"
            case "complete_cancel":
                if self.status == "filled":
                    return None  # The pending order filled before completion.
                if self.status != "pending_cancel":
                    raise ScenarioValidationError(
                        f"leg {event.leg} completion requires a pending request"
                    )
                self.status = "closed"
            case "sell":
                raise AssertionError("sell arrivals require volume allocation")
        return ScenarioEvent(event.leg, event.kind)


def _evaluate(spec: QueueScenarioSpec) -> QueueScenarioResult:
    if type(spec) is not QueueScenarioSpec:
        raise ScenarioValidationError("expected a QueueScenarioSpec")
    cutoff = _nonnegative_int(spec.cutoff_ms, "cutoff")
    schedule = _schedule("A", spec.leg_a) + _schedule("B", spec.leg_b)
    schedule.sort(key=_Scheduled.sort_key)
    for first, second in pairwise(schedule):
        if first.leg == second.leg and first.time_ms == second.time_ms:
            if first.order is None or first.order == second.order:
                raise ScenarioValidationError(
                    f"leg {first.leg} tied events require distinct explicit orders"
                )

    legs = {"A": spec.leg_a, "B": spec.leg_b}
    queues = {leg: _Queue(params.quantity) for leg, params in legs.items()}
    trace: list[ArrivalTrace] = []
    events: list[ScenarioEvent] = []
    # Validate the whole history, retaining only allocations and events through cutoff.
    for event in schedule:
        queue = queues[event.leg]
        params = legs[event.leg]
        if event.kind == "sell":
            arrival = queue.sell(event)
            if event.time_ms <= cutoff:
                trace.append(arrival)
                if arrival.filled:
                    events.append(
                        ScenarioEvent(event.leg, "fill", arrival.filled, params.price_usd)
                    )
        else:
            derived = queue.transition(event, params)
            if derived is not None and event.time_ms <= cutoff:
                events.append(derived)

    ordered = tuple(events)
    # All fills and whether a requested cancellation completed are known through cutoff.
    knowledge = CutoffKnowledge(fills_complete=True, cancellation_completion_known=True)
    accounting = simulation.evaluate_scenario(
        ScenarioSpec(
            spec.leg_a.quantity,
            spec.leg_b.quantity,
            ordered,
            knowledge,
            knowledge,
            spec.payout_table,
        )
    )
    return QueueScenarioResult(tuple(trace), ordered, accounting)


def evaluate_queue_scenario(spec: QueueScenarioSpec) -> QueueScenarioResult:
    """Match both buy queues and replay their accounting events through the inclusive cutoff.

    Every scheduled event tied on leg and millisecond needs a distinct nonnegative
    order. Lower orders run first. Invalid inputs or histories anywhere in the
    schedule raise ScenarioValidationError.
    """
    # Each subtraction stays within the input's 12 integer and 8 fractional digits.
    # Gross costs and payouts use the public accounting evaluator's own exact context.
    with localcontext(
        Context(
            prec=20,
            rounding=ROUND_HALF_EVEN,
            Emin=-8,
            Emax=11,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[Inexact, Rounded, InvalidOperation, Overflow],
        )
    ):
        try:
            return _evaluate(spec)
        except AttributeError:
            raise ScenarioValidationError("queue scenario has an uninitialized field") from None
