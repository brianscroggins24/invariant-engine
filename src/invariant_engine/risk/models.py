"""Immutable fixture inputs and reports for standalone synthetic risk checks."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

ObservationKind = Literal[
    "kill_switch",
    "gross_edge_lower",
    "costs_upper",
    "existing_exposure",
    "loss_if_a_fails",
    "loss_if_b_fails",
]
ObservationUnit = Literal["boolean", "USD"]
CheckName = Literal[
    "strategy_enablement", "kill_switch", "freshness", "minimum_edge", "leg_size", "exposure"
]
CheckUnit = Literal["boolean", "USD", "units", "duration"]
CheckValue = bool | Decimal | timedelta
RiskStatus = Literal["PASS", "BLOCK"]
CheckReason = Literal[
    "strategy_enabled",
    "strategy_disabled",
    "enablement_not_explicit",
    "switch_clear",
    "switch_active",
    "unusable_evidence",
    "fresh",
    "at_least_minimum",
    "below_minimum",
    "within_cap",
    "above_cap",
]
EvidenceReason = Literal[
    "missing_observation", "unknown_value", "missing_timestamp", "future_dated", "stale"
]


class RiskValidationError(ValueError):
    """The entire evaluation was rejected due to malformed or mismatched input."""


@dataclass(frozen=True, slots=True)
class RiskScope:
    """Exact strategy, caller-named decision scope, and ordered leg identifiers."""

    strategy_id: str
    scope_id: str
    leg_ids: tuple[str, str]


@dataclass(frozen=True, slots=True)
class RiskProposal:
    """A synthetic buy of both legs, with quantities in corresponding leg units."""

    scope: RiskScope
    quantities: tuple[Decimal, Decimal]
    decision_time: datetime


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Independent policy for the exact scope, applicable across quantities.

    None means enablement was not explicitly established. Size caps are in
    corresponding leg units. Edge and exposure limits are total USD amounts.
    """

    policy_id: str
    version: str
    scope: RiskScope
    strategy_enabled: bool | None
    max_observation_age: timedelta
    min_edge_usd: Decimal
    leg_caps: tuple[Decimal, Decimal]
    exposure_cap_usd: Decimal


@dataclass(frozen=True, slots=True)
class RiskObservation:
    """One role-labeled, proposal-bound fixture observation.

    The kill switch is boolean, with True meaning active. All other values
    are total USD amounts for the specified role. Costs include all applicable
    costs, including fees, and the two named losses are fixture assumptions
    for failure of the corresponding ordered leg alone. None means the value
    or timestamp is unknown. A timestamp must use a fixed UTC offset.
    """

    kind: ObservationKind
    bound_proposal: RiskProposal
    value: bool | Decimal | None
    observed_at: datetime | None
    unit: ObservationUnit


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    """Independent state for the exact proposal, with None for missing rows."""

    bound_proposal: RiskProposal
    kill_switch: RiskObservation | None = None
    gross_edge_lower: RiskObservation | None = None
    costs_upper: RiskObservation | None = None
    existing_exposure: RiskObservation | None = None
    loss_if_a_fails: RiskObservation | None = None
    loss_if_b_fails: RiskObservation | None = None


@dataclass(frozen=True, slots=True)
class EvidenceIssue:
    observation: ObservationKind
    reason: EvidenceReason


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """One check, with a comparable value and limit in the given unit when known.

    Freshness values and upper limits are durations with an implicit zero
    lower bound. Observation and leg identifiers distinguish repeated checks.
    """

    name: CheckName
    status: RiskStatus
    value: CheckValue | None
    unit: CheckUnit
    limit: CheckValue
    reason: CheckReason
    observation: ObservationKind | None = None
    leg_id: str | None = None
    evidence_issues: tuple[EvidenceIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class RiskReport:
    """Synthetic result only. No trading permission, reservation or order."""

    status: RiskStatus
    proposal: RiskProposal
    policy_id: str
    policy_version: str
    checks: tuple[RiskCheck, ...]
    actionable: Literal[False] = field(default=False, init=False)
    reserves_capital: Literal[False] = field(default=False, init=False)
