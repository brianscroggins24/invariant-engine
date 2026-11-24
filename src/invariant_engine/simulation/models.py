"""Immutable inputs and outputs for a conditional two-leg synthetic scenario."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Leg = Literal["A", "B"]
EventKind = Literal["open", "reject", "fill", "request_cancel", "complete_cancel"]
LegStatus = Literal["awaiting_outcome", "open", "pending_cancel", "rejected", "filled", "canceled"]
Uncertainty = Literal["incomplete_fills", "unknown_cancellation_completion"]


class ScenarioValidationError(ValueError):
    """The entire scenario was rejected. Transition errors identify the event index."""


@dataclass(frozen=True, slots=True)
class ScenarioEvent:
    """An event for one leg. Only fills carry quantity and USD price per unit."""

    leg: Leg
    kind: EventKind
    quantity: Decimal | None = None
    price_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CutoffKnowledge:
    """Declare completeness of fills and, if pending, cancellation completion.

    For a pending request at the end of the supplied history, True confirms
    that completion did not occur through cutoff; False leaves it unknown.
    None is allowed when the supplied history has no pending request.
    Incomplete fill knowledge only concerns fills compatible with that history.
    """

    fills_complete: bool
    cancellation_completion_known: bool | None = None


@dataclass(frozen=True, slots=True)
class HypotheticalPayout:
    """USD per acquired unit in one caller-named hypothetical settlement state."""

    name: str
    leg_a_usd_per_unit: Decimal
    leg_b_usd_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """Intended buy quantities, caller-ordered events, and knowledge at cutoff.

    Each leg starts with zero holdings. An empty payout table omits payouts.
    """

    leg_a_quantity: Decimal
    leg_b_quantity: Decimal
    events: tuple[ScenarioEvent, ...]
    leg_a_cutoff: CutoffKnowledge
    leg_b_cutoff: CutoffKnowledge
    payout_table: tuple[HypotheticalPayout, ...] = ()


@dataclass(frozen=True, slots=True)
class LegState:
    """One leg's accounting through a prefix of the supplied event sequence."""

    intended_quantity: Decimal
    status: LegStatus
    acquired_quantity: Decimal
    open_quantity: Decimal
    closed_unfilled_quantity: Decimal
    awaiting_outcome_quantity: Decimal
    gross_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class EventResult:
    """Both legs immediately after the supplied event at the zero-based index."""

    event_index: int
    event: ScenarioEvent
    leg_a: LegState
    leg_b: LegState
    fill_cost_usd: Decimal | None
    gross_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class CutoffLegResult:
    """Final values established at cutoff, with None for unavailable values.

    Incomplete fills can affect acquired, gross cost, and the remaining
    quantity. Unknown cancellation completion can affect the open and
    closed-unfilled split. Either can leave the final status unavailable.
    The supplied state is the ledger before accounting for this uncertainty.
    """

    supplied_state: LegState
    status: LegStatus | None
    acquired_quantity: Decimal | None
    open_quantity: Decimal | None
    closed_unfilled_quantity: Decimal | None
    gross_cost_usd: Decimal | None
    uncertainty: tuple[Uncertainty, ...]

    @property
    def intended_quantity(self) -> Decimal:
        return self.supplied_state.intended_quantity

    @property
    def awaiting_outcome_quantity(self) -> Decimal:
        return self.supplied_state.awaiting_outcome_quantity

    @property
    def confirmed_acquired_quantity(self) -> Decimal:
        return self.supplied_state.acquired_quantity

    @property
    def confirmed_gross_cost_usd(self) -> Decimal:
        return self.supplied_state.gross_cost_usd


@dataclass(frozen=True, slots=True)
class PayoutResult:
    """Gross USD amounts for one hypothetical state, or None if unavailable."""

    name: str
    leg_a_payout_usd: Decimal | None
    leg_b_payout_usd: Decimal | None
    gross_payout_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Synthetic accounting conditional on the caller's assumptions."""

    events: tuple[EventResult, ...]
    leg_a: CutoffLegResult
    leg_b: CutoffLegResult
    confirmed_gross_cost_usd: Decimal
    gross_cost_usd: Decimal | None
    payouts: tuple[PayoutResult, ...]
    conditional: Literal[True] = field(default=True, init=False)
    actionable: Literal[False] = field(default=False, init=False)
