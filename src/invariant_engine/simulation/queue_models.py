"""Immutable assumptions and results for two independent synthetic buy queues."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from invariant_engine.simulation import HypotheticalPayout, ScenarioEvent, ScenarioResult


@dataclass(frozen=True, slots=True)
class SellArrival:
    """Incoming volume. Lower order runs first within a same-leg millisecond."""

    time_ms: int
    volume: Decimal
    order: int | None = None


@dataclass(frozen=True, slots=True)
class Cancellation:
    """A request and its scheduled completion, each with its own tie order."""

    request_ms: int
    delay_ms: int
    request_order: int | None = None
    completion_order: int | None = None


@dataclass(frozen=True, slots=True)
class QueueLegSpec:
    """Supply volume ahead at opening, or None for a rejection."""

    quantity: Decimal
    price_usd: Decimal
    submission_ms: int
    processing_delay_ms: int
    outcome: Literal["open", "reject"]
    ahead_at_open: Decimal | None
    arrivals: tuple[SellArrival, ...] = ()
    cancellation: Cancellation | None = None
    outcome_order: int | None = None


@dataclass(frozen=True, slots=True)
class QueueScenarioSpec:
    """Both legs start empty. The common cutoff includes its entire millisecond."""

    leg_a: QueueLegSpec
    leg_b: QueueLegSpec
    cutoff_ms: int
    payout_table: tuple[HypotheticalPayout, ...] = ()


@dataclass(frozen=True, slots=True)
class ArrivalTrace:
    """The allocation of one arrival at its position in the ordered history."""

    leg: Literal["A", "B"]
    time_ms: int
    order: int | None
    volume: Decimal
    consumed_ahead: Decimal
    filled: Decimal
    unused: Decimal


@dataclass(frozen=True, slots=True)
class QueueScenarioResult:
    """Volume allocations and public accounting conditional on the supplied assumptions."""

    trace: tuple[ArrivalTrace, ...]
    events: tuple[ScenarioEvent, ...]
    accounting: ScenarioResult
    conditional: Literal[True] = field(default=True, init=False)
    actionable: Literal[False] = field(default=False, init=False)
