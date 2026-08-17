"""Immutable records for bounded historical opportunity economics.

The records in this module describe a deterministic counterfactual calculation.
They do not describe an order, execution, recommendation, or authorization.
"""

import hashlib
import weakref
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import SupportsIndex, cast

from invariant_engine.domain.decimal_policy import parse_decimal, parse_quantity
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, RawReference, Venue
from invariant_engine.relationships.candidates import RelationshipType
from invariant_engine.relationships.ids import CertificateId, ClaimBindingId
from invariant_engine.serialization import stable_json_bytes

OPPORTUNITY_SCHEMA_VERSION = "opportunity-economics-v1"
FEE_POLICY_SCHEMA_VERSION = "fee-policy-v1"


class OpportunityEconomicsStatus(StrEnum):
    VALIDATED = "validated"
    NO_NET_EDGE = "no_net_edge"
    INSUFFICIENT_DEPTH = "insufficient_depth"
    UNSUPPORTED_TRADE_DIRECTION = "unsupported_trade_direction"
    UNAVAILABLE = "unavailable"


OpportunityEconomicsEvaluationStatus = OpportunityEconomicsStatus


class OpportunityReasonCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    INVALID_CERTIFICATE = "invalid_certificate"
    INVALID_CONSTRAINT = "invalid_constraint"
    CONSTRAINT_MISMATCH = "constraint_mismatch"
    INVALID_QUANTITY = "invalid_quantity"
    MISSING_SNAPSHOT = "missing_snapshot"
    EXTRA_SNAPSHOT = "extra_snapshot"
    INVALID_SNAPSHOT = "invalid_snapshot"
    OBSERVATION_FAILURE = "observation_failure"
    UPSTREAM_NOT_VIOLATED = "upstream_not_violated"
    UNSUPPORTED_TRADE_DIRECTION = "unsupported_trade_direction"
    INSUFFICIENT_DEPTH = "insufficient_depth"
    MISSING_FEE_POLICY = "missing_fee_policy"
    DUPLICATE_FEE_POLICY = "duplicate_fee_policy"
    INVALID_FEE_POLICY = "invalid_fee_policy"
    INEFFECTIVE_FEE_POLICY = "ineffective_fee_policy"
    CURRENCY_INCOMPATIBLE = "currency_incompatible"
    NO_NET_EDGE = "no_net_edge"
    INTERNAL_REPRESENTATION = "internal_representation_failure"


@dataclass(frozen=True, slots=True)
class OpportunityReason:
    code: OpportunityReasonCode
    message: str
    claim_binding_id: ClaimBindingId | None = None
    state_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecimalInterval:
    """A closed, finite Decimal interval used for historical uncertainty."""

    lower: Decimal
    upper: Decimal

    def __post_init__(self) -> None:
        lower = parse_decimal(self.lower, field="interval lower")
        upper = parse_decimal(self.upper, field="interval upper")
        if lower > upper:
            raise DomainError("interval lower must not exceed upper")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)


class FeeRole(StrEnum):
    TAKER = "taker"
    MAKER = "maker"


class FeeTradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class FeeFormulaKind(StrEnum):
    ZERO = "zero"
    QUADRATIC_PRICE = "quadratic_price"
    FLAT_PER_CONTRACT = "flat_per_contract"


class FeeCalculationScope(StrEnum):
    PER_DEPTH_SLICE = "per_depth_slice"
    PER_LEG_AGGREGATE = "per_leg_aggregate"


class FeeRoundingScope(StrEnum):
    EACH_CALCULATION_COMPONENT = "each_calculation_component"
    LEG_TOTAL = "leg_total"


# Public aliases make the explicit vocabulary easy to discover without adding
# a second, divergent policy model.
LiquidityRole = FeeRole
TradeSide = FeeTradeSide
FeeFormula = FeeFormulaKind
CalculationScope = FeeCalculationScope
RoundingScope = FeeRoundingScope

_ROUNDING_MODES = frozenset(
    {
        "ROUND_CEILING",
        "ROUND_DOWN",
        "ROUND_FLOOR",
        "ROUND_HALF_DOWN",
        "ROUND_HALF_EVEN",
        "ROUND_HALF_UP",
        "ROUND_UP",
        "ROUND_05UP",
    }
)


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f"{field} must be timezone-aware")
    return value


def _ordered_unique_refs(value: object, field: str, venue: Venue) -> tuple[RawReference, ...]:
    if not isinstance(value, tuple):
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            raise DomainError(f"{field} must be an iterable of RawReference values")
        value = tuple(value)
    refs = cast(tuple[object, ...], value)
    if not refs or any(not isinstance(item, RawReference) for item in refs):
        raise DomainError(f"{field} must be a non-empty tuple of RawReference values")
    result = cast(tuple[RawReference, ...], refs)
    if any(item.venue is not venue for item in result) or len(set(result)) != len(result):
        raise DomainError(f"{field} must contain unique references for the policy venue")
    return result


@dataclass(frozen=True, slots=True)
class FeePolicy:
    schema_version: str
    policy_id: str
    venue: Venue
    effective_start: datetime
    effective_end: datetime
    start_inclusive: bool
    end_inclusive: bool
    role: FeeRole
    trade_side: FeeTradeSide
    formula_kind: FeeFormulaKind
    formula_parameters: tuple[tuple[str, DecimalInterval], ...]
    calculation_scope: FeeCalculationScope
    rounding_scope: FeeRoundingScope
    rounding_mode: str
    currency: str
    rounding_quantum: Decimal
    provenance: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FEE_POLICY_SCHEMA_VERSION:
            raise DomainError("unsupported fee policy schema version")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise DomainError("fee policy ID must be non-empty")
        if not isinstance(self.venue, Venue):
            raise DomainError("fee policy venue must be a Venue")
        start = _aware(self.effective_start, "effective_start")
        end = _aware(self.effective_end, "effective_end")
        if start.astimezone(UTC) > end.astimezone(UTC):
            raise DomainError("fee policy effective interval is inverted")
        if not isinstance(self.start_inclusive, bool) or not isinstance(self.end_inclusive, bool):
            raise DomainError("fee policy interval boundaries must be explicit booleans")
        if not isinstance(self.role, FeeRole) or not isinstance(self.trade_side, FeeTradeSide):
            raise DomainError("fee policy role and trade side are unsupported")
        if not isinstance(self.formula_kind, FeeFormulaKind):
            raise DomainError("fee policy formula kind is unsupported")
        parameters: object = self.formula_parameters
        if isinstance(parameters, Mapping):
            parameters = tuple(sorted(parameters.items(), key=lambda item: str(item[0])))
        elif not isinstance(parameters, tuple):
            if not isinstance(parameters, Iterable) or isinstance(parameters, (str, bytes)):
                raise DomainError("fee formula parameters must be named interval pairs")
            parameters = tuple(parameters)
        normalized: list[tuple[str, DecimalInterval]] = []
        for item in cast(tuple[object, ...], parameters):
            if not isinstance(item, tuple) or len(item) != 2:
                raise DomainError("fee formula parameters must be named interval pairs")
            name, interval = item
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(interval, DecimalInterval)
            ):
                raise DomainError("fee formula parameters must be Decimal intervals")
            normalized.append((name, interval))
        names = tuple(item[0] for item in normalized)
        if len(set(names)) != len(names):
            raise DomainError("fee formula parameter names must be unique")
        expected = {
            FeeFormulaKind.ZERO: (),
            FeeFormulaKind.QUADRATIC_PRICE: ("rate",),
            FeeFormulaKind.FLAT_PER_CONTRACT: ("amount",),
        }[self.formula_kind]
        if names != expected:
            raise DomainError("fee formula parameters are incomplete or contain extras")
        if any(interval.lower < 0 for _, interval in normalized):
            raise DomainError("fee formula parameters must not be negative")
        object.__setattr__(self, "formula_parameters", tuple(normalized))
        if not isinstance(self.calculation_scope, FeeCalculationScope):
            raise DomainError("fee calculation scope is unsupported")
        if not isinstance(self.rounding_scope, FeeRoundingScope):
            raise DomainError("fee rounding scope is unsupported")
        if self.rounding_mode not in _ROUNDING_MODES:
            raise DomainError("fee rounding mode is unsupported")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise DomainError("fee currency must be non-empty")
        quantum = parse_decimal(self.rounding_quantum, field="rounding quantum")
        if quantum <= 0:
            raise DomainError("rounding quantum must be positive")
        object.__setattr__(self, "rounding_quantum", quantum)
        object.__setattr__(
            self,
            "provenance",
            _ordered_unique_refs(self.provenance, "fee policy provenance", self.venue),
        )

    @property
    def parameters(self) -> tuple[tuple[str, DecimalInterval], ...]:
        return self.formula_parameters

    def applies_at(self, instant: datetime) -> bool:
        instant = _aware(instant, "policy comparison instant").astimezone(UTC)
        start = self.effective_start.astimezone(UTC)
        end = self.effective_end.astimezone(UTC)
        return (instant > start or (self.start_inclusive and instant == start)) and (
            instant < end or (self.end_inclusive and instant == end)
        )


@dataclass(frozen=True, slots=True)
class FeePolicyAssignment:
    claim_binding_id: ClaimBindingId
    policy: FeePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.claim_binding_id, ClaimBindingId):
            raise DomainError("fee assignment requires a ClaimBindingId")
        if not isinstance(self.policy, FeePolicy):
            raise DomainError("fee assignment requires a FeePolicy")


@dataclass(frozen=True, slots=True)
class DepthSlice:
    index: int
    quantity: Decimal
    price: Decimal
    cost: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise DomainError("depth slice index must be a non-negative integer")
        quantity = parse_quantity(self.quantity, field="depth slice quantity")
        price = parse_decimal(self.price, field="depth slice price")
        cost = parse_decimal(self.cost, field="depth slice cost")
        if quantity <= 0 or price < 0 or cost < 0:
            raise DomainError("depth slice values are invalid")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "cost", cost)


@dataclass(frozen=True, slots=True)
class LegEconomics:
    claim_binding_id: ClaimBindingId
    proposition_id: object
    venue: Venue
    market: object
    contract: ContractReference | None
    native_claim_side: str | None
    snapshot_identity: str
    snapshot_schema_version: str
    snapshot_price_convention: str | None
    observation_id: str
    timestamp: datetime
    raw_refs: tuple[RawReference, ...]
    required_quantity: Decimal
    observed_ask_capacity: Decimal
    depth_slices: tuple[DepthSlice, ...]
    total_purchase_cost: Decimal
    vwap: Decimal
    fee_policy_id: str | None = None
    fee_policy: FeePolicy | None = None
    fee_policy_provenance: tuple[RawReference, ...] = ()
    fee_interval: DecimalInterval | None = None


@dataclass(frozen=True, slots=True)
class StateEconomics:
    state_id: str
    terminal_kind: object
    gross_payoff: Decimal
    gross_edge: Decimal
    net_edge_lower: Decimal
    net_edge_upper: Decimal


@dataclass(frozen=True, slots=True)
class ResidualFailureState:
    state_id: str
    terminal_kind: object
    gross_payoff: Decimal
    gross_pnl: Decimal
    fee_interval: DecimalInterval
    net_pnl_lower: Decimal
    net_pnl_upper: Decimal


@dataclass(frozen=True, slots=True)
class ResidualFailureScenario:
    failed_claim_binding_id: ClaimBindingId
    successful_claim_binding_ids: tuple[ClaimBindingId, ...]
    states: tuple[ResidualFailureState, ...]
    minimum_net_pnl: Decimal
    minimum_state_id: str
    maximum_net_pnl: Decimal
    maximum_state_id: str


@dataclass(frozen=True, slots=True)
class OpportunityEconomicsEvaluation:
    schema_version: str
    evaluation_id: str
    status: OpportunityEconomicsStatus
    certificate_id: CertificateId | None
    constraint_id: object | None
    fresh_constraint_evaluation_id: object | None
    certificate_material: object | None
    supplied_constraint_material: object | None
    reconstructed_constraint_material: object | None
    fresh_constraint_evaluation_material: object | None
    relationship_type: RelationshipType | None
    quantity: Decimal | None
    common_timestamp: datetime | None
    currency: str | None
    legs: tuple[LegEconomics, ...]
    total_purchase_cost: Decimal | None
    total_fee_interval: DecimalInterval | None
    state_results: tuple[StateEconomics, ...]
    aggregate_gross_edge: DecimalInterval | None
    aggregate_net_edge: DecimalInterval | None
    residual_failures: tuple[ResidualFailureScenario, ...]
    certificate_provenance: tuple[RawReference, ...]
    observation_provenance: tuple[RawReference, ...]
    fee_provenance: tuple[RawReference, ...]
    combined_provenance: tuple[RawReference, ...]
    warnings: tuple[object, ...]
    reasons: tuple[OpportunityReason, ...]

    def __post_init__(self) -> None:
        if self.schema_version != OPPORTUNITY_SCHEMA_VERSION:
            raise DomainError("unsupported opportunity economics schema version")
        if not isinstance(self.evaluation_id, str) or not self.evaluation_id.startswith(
            "opportunity-evaluation:"
        ):
            raise DomainError("evaluation_id must use the opportunity-evaluation prefix")
        if not isinstance(self.status, OpportunityEconomicsStatus):
            raise DomainError("opportunity status must be an OpportunityEconomicsStatus")
        if self.quantity is not None:
            object.__setattr__(self, "quantity", parse_quantity(self.quantity, field="quantity"))
        for field in (
            "legs",
            "state_results",
            "residual_failures",
            "certificate_provenance",
            "observation_provenance",
            "fee_provenance",
            "combined_provenance",
            "warnings",
            "reasons",
        ):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if self.common_timestamp is not None:
            _aware(self.common_timestamp, "common_timestamp")
        if self.total_purchase_cost is not None:
            object.__setattr__(
                self,
                "total_purchase_cost",
                parse_decimal(self.total_purchase_cost, field="total_purchase_cost"),
            )


@dataclass(frozen=True, slots=True)
class OpportunityEconomicsResult:
    evaluation: OpportunityEconomicsEvaluation
    candidate: "OpportunityCandidate | None" = None

    @property
    def status(self) -> OpportunityEconomicsStatus:
        return self.evaluation.status


_CANDIDATE_TRUST_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _CandidateTrustEntry:
    reference: weakref.ReferenceType[object]
    commitment: str


_TRUSTED_CANDIDATES: dict[int, _CandidateTrustEntry] = {}


def _remove_candidate_trust(key: int, reference: weakref.ReferenceType[object]) -> None:
    entry = _TRUSTED_CANDIDATES.get(key)
    if entry is not None and entry.reference is reference:
        _TRUSTED_CANDIDATES.pop(key, None)


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class OpportunityCandidate:
    """Evaluator-produced, explicitly non-actionable opportunity finding."""

    schema_version: str
    candidate_id: str
    economics_evaluation: OpportunityEconomicsEvaluation
    non_actionable: bool

    @classmethod
    def _from_evaluator(
        cls, evaluation: OpportunityEconomicsEvaluation, *, token: object
    ) -> "OpportunityCandidate":
        if token is not _CANDIDATE_TRUST_TOKEN:
            raise DomainError("candidate trust may only be issued by the economics evaluator")
        if evaluation.status is not OpportunityEconomicsStatus.VALIDATED:
            raise DomainError("only validated economics may produce a candidate")
        content = {
            "schema_version": OPPORTUNITY_SCHEMA_VERSION,
            "economics_evaluation": evaluation,
            "non_actionable": True,
        }
        digest = hashlib.sha256(stable_json_bytes(content)).hexdigest()
        candidate = object.__new__(cls)
        object.__setattr__(candidate, "schema_version", OPPORTUNITY_SCHEMA_VERSION)
        object.__setattr__(candidate, "candidate_id", "opportunity-candidate:" + digest)
        object.__setattr__(candidate, "economics_evaluation", evaluation)
        object.__setattr__(candidate, "non_actionable", True)

        key = id(candidate)

        def cleanup(reference: weakref.ReferenceType[object]) -> None:
            _remove_candidate_trust(key, reference)

        _TRUSTED_CANDIDATES[key] = _CandidateTrustEntry(weakref.ref(candidate, cleanup), digest)
        return candidate

    @property
    def evaluation(self) -> OpportunityEconomicsEvaluation:
        return self.economics_evaluation

    def __deepcopy__(self, memo: dict[int, object]) -> "OpportunityCandidate":
        """Copy material without copying the process-local trust entry."""

        clone = object.__new__(type(self))
        memo[id(self)] = clone
        for field_name in (
            "schema_version",
            "candidate_id",
            "economics_evaluation",
            "non_actionable",
        ):
            object.__setattr__(clone, field_name, getattr(self, field_name))
        return clone

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[object, tuple[object, ...]]:
        """Pickle only a deliberately untrusted reconstruction."""

        del protocol
        return (_reconstruct_untrusted_candidate, (self.schema_version, self.candidate_id))


def _reconstruct_untrusted_candidate(
    schema_version: str, candidate_id: str
) -> OpportunityCandidate:
    candidate = object.__new__(OpportunityCandidate)
    object.__setattr__(candidate, "schema_version", schema_version)
    object.__setattr__(candidate, "candidate_id", candidate_id)
    object.__setattr__(candidate, "economics_evaluation", None)
    object.__setattr__(candidate, "non_actionable", True)
    return candidate


def candidate_identity_content(candidate: OpportunityCandidate) -> dict[str, object]:
    return {
        "schema_version": candidate.schema_version,
        "economics_evaluation": candidate.economics_evaluation,
        "non_actionable": candidate.non_actionable,
    }


def is_trusted_candidate(value: object) -> bool:
    if type(value) is not OpportunityCandidate:
        return False
    entry = _TRUSTED_CANDIDATES.get(id(value))
    if entry is None or entry.reference() is not value:
        return False
    try:
        content = candidate_identity_content(value)
        digest = hashlib.sha256(stable_json_bytes(content)).hexdigest()
        return (
            digest == entry.commitment
            and value.schema_version == OPPORTUNITY_SCHEMA_VERSION
            and value.candidate_id == "opportunity-candidate:" + digest
            and value.non_actionable is True
            and value.economics_evaluation.status is OpportunityEconomicsStatus.VALIDATED
        )
    except Exception:
        return False


__all__ = [
    "CalculationScope",
    "DecimalInterval",
    "DepthSlice",
    "FeeCalculationScope",
    "FeeFormula",
    "FeeFormulaKind",
    "FeePolicy",
    "FeePolicyAssignment",
    "FeeRole",
    "FeeRoundingScope",
    "FeeTradeSide",
    "FEE_POLICY_SCHEMA_VERSION",
    "LegEconomics",
    "LiquidityRole",
    "OpportunityCandidate",
    "OpportunityEconomicsEvaluation",
    "OpportunityEconomicsEvaluationStatus",
    "OpportunityEconomicsResult",
    "OpportunityEconomicsStatus",
    "OpportunityReason",
    "OpportunityReasonCode",
    "OPPORTUNITY_SCHEMA_VERSION",
    "ResidualFailureScenario",
    "ResidualFailureState",
    "RoundingScope",
    "StateEconomics",
    "TradeSide",
    "candidate_identity_content",
    "is_trusted_candidate",
]
