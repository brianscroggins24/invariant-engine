"""Immutable, versioned records for deterministic diagnostic constraints.

This module contains only the records that cross the Milestone 2.3 boundary.
The records deliberately describe quote intervals and mathematical results;
they do not describe economic actions or authorization.
"""

import hashlib
import weakref
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from invariant_engine.domain.decimal_policy import parse_decimal, parse_price
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningRecord
from invariant_engine.relationships.candidates import RelationshipType
from invariant_engine.relationships.claims import ClaimClassification
from invariant_engine.relationships.ids import (
    CertificateId,
    ClaimBindingId,
    PropositionId,
)
from invariant_engine.serialization import stable_json_bytes

CONSTRAINT_SCHEMA_VERSION = "constraint-v1"
OBSERVATION_SCHEMA_VERSION = "quote-observation-v1"
EVALUATION_SCHEMA_VERSION = "constraint-evaluation-v1"

# These tokens are intentionally private to the constraints implementation.
# The evaluator accepts only records marked with the corresponding producer
# token; ordinary construction remains an untrusted proposal.
_CONSTRAINT_TRUST_TOKEN = object()
_OBSERVATION_TRUST_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _TrustEntry:
    reference: weakref.ReferenceType[object]
    commitment: str


_TRUSTED_CONSTRAINTS: dict[int, _TrustEntry] = {}
_TRUSTED_OBSERVATIONS: dict[int, _TrustEntry] = {}


def _remove_trust(
    registry: dict[int, _TrustEntry],
    key: int,
    reference: weakref.ReferenceType[object],
) -> None:
    raw_entry: object = registry.get(key)
    current_reference = (
        raw_entry.reference
        if isinstance(raw_entry, _TrustEntry)
        else cast(weakref.ReferenceType[object] | None, raw_entry)
    )
    if current_reference is reference:
        registry.pop(key, None)


def _record_trust(registry: dict[int, _TrustEntry], value: object, commitment: str) -> None:
    key = id(value)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        _remove_trust(registry, key, reference)

    registry[key] = _TrustEntry(weakref.ref(value, cleanup), commitment)


def _registry_entry(registry: dict[int, _TrustEntry], value: object) -> _TrustEntry | None:
    entry = registry.get(id(value))
    if entry is None or entry.reference() is not value:
        return None
    return entry


def _content_commitment(content: dict[str, object]) -> str:
    return hashlib.sha256(stable_json_bytes(content)).hexdigest()


@dataclass(frozen=True, slots=True)
class ConstraintId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.startswith("constraint:"):
            raise DomainError("constraint ID must use the constraint: prefix")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EvaluationId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.startswith("evaluation:"):
            raise DomainError("evaluation ID must use the evaluation: prefix")

    def __str__(self) -> str:
        return self.value


class ConstraintRelation(StrEnum):
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="
    EQUAL = "="
    LE = "<="
    GE = ">="
    EQ = "="


RelationOperator = ConstraintRelation
ConstraintRelationOperator = ConstraintRelation


@dataclass(frozen=True, slots=True)
class LinearTerm:
    proposition_id: PropositionId
    claim_binding_id: ClaimBindingId
    coefficient: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.proposition_id, PropositionId):
            raise DomainError("linear term proposition_id must be a PropositionId")
        if not isinstance(self.claim_binding_id, ClaimBindingId):
            raise DomainError("linear term claim_binding_id must be a ClaimBindingId")
        object.__setattr__(
            self, "coefficient", parse_decimal(self.coefficient, field="term coefficient")
        )


@dataclass(frozen=True, slots=True)
class ClaimBindingIdentity:
    """The venue-native identity needed to close an observation to a term."""

    proposition_id: PropositionId
    claim_binding_id: ClaimBindingId
    classification: ClaimClassification
    venue: Venue
    market: MarketReference | object
    contract: ContractReference | None = None
    native_side: str | None = None
    native_outcome_side: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.proposition_id, PropositionId):
            raise DomainError("binding identity proposition_id must be a PropositionId")
        if not isinstance(self.claim_binding_id, ClaimBindingId):
            raise DomainError("binding identity claim_binding_id must be a ClaimBindingId")
        if not isinstance(self.classification, ClaimClassification):
            raise DomainError("binding identity classification must be ClaimClassification")
        if not isinstance(self.venue, Venue):
            raise DomainError("binding identity venue must be a Venue")
        if self.venue is Venue.POLYMARKET:
            if not isinstance(self.market, MarketReference) or self.market.venue is not self.venue:
                raise DomainError("Polymarket binding identity requires a Polymarket market")
            if (
                not isinstance(self.contract, ContractReference)
                or self.contract.venue is not self.venue
            ):
                raise DomainError("Polymarket binding identity requires a Polymarket token")
            if self.native_side is not None and not isinstance(self.native_side, str):
                raise DomainError("Polymarket native side must be a string when supplied")
        else:
            from invariant_engine.venues.kalshi import KalshiMarketIdentity

            if not isinstance(self.market, KalshiMarketIdentity):
                raise DomainError("Kalshi binding identity requires a Kalshi market")
            if self.contract is not None:
                raise DomainError("Kalshi binding identity cannot contain a contract")
            if not isinstance(self.native_side, str) or not self.native_side.strip():
                raise DomainError("Kalshi binding identity requires a native side")
            if self.native_outcome_side is not None:
                raise DomainError("Kalshi binding identity cannot contain a Polymarket side")


@dataclass(frozen=True, slots=True)
class CompiledPricingConstraint:
    schema_version: str
    constraint_id: ConstraintId
    certificate_id: CertificateId
    certificate_schema_version: str
    certificate_validation_fingerprint: str
    relationship_type: RelationshipType
    terms: tuple[LinearTerm, ...]
    relation: ConstraintRelation
    bound: Decimal
    certificate_provenance: tuple[RawReference, ...]
    binding_identities: tuple[ClaimBindingIdentity, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONSTRAINT_SCHEMA_VERSION:
            raise DomainError("unsupported constraint schema version")
        if not isinstance(self.constraint_id, ConstraintId):
            raise DomainError("constraint_id must be a ConstraintId")
        if not isinstance(self.certificate_id, CertificateId):
            raise DomainError("certificate_id must be a CertificateId")
        if (
            not isinstance(self.certificate_schema_version, str)
            or not self.certificate_schema_version
        ):
            raise DomainError("certificate schema version must be non-empty")
        if (
            not isinstance(self.certificate_validation_fingerprint, str)
            or not self.certificate_validation_fingerprint
        ):
            raise DomainError("certificate validation fingerprint must be non-empty")
        if not isinstance(self.relationship_type, RelationshipType):
            raise DomainError("relationship_type must be a RelationshipType")
        if not isinstance(self.terms, tuple):
            object.__setattr__(self, "terms", tuple(self.terms))
        if not self.terms or any(not isinstance(term, LinearTerm) for term in self.terms):
            raise DomainError("constraint terms must be non-empty LinearTerm values")
        if not isinstance(self.relation, ConstraintRelation):
            raise DomainError("constraint relation must be a ConstraintRelation")
        object.__setattr__(self, "bound", parse_decimal(self.bound, field="constraint bound"))
        if not isinstance(self.certificate_provenance, tuple):
            object.__setattr__(self, "certificate_provenance", tuple(self.certificate_provenance))
        if not self.certificate_provenance or any(
            not isinstance(item, RawReference) for item in self.certificate_provenance
        ):
            raise DomainError("constraint certificate provenance must be non-empty RawReferences")
        if not isinstance(self.binding_identities, tuple):
            object.__setattr__(self, "binding_identities", tuple(self.binding_identities))
        if len(self.binding_identities) != len(self.terms) or any(
            not isinstance(item, ClaimBindingIdentity) for item in self.binding_identities
        ):
            raise DomainError("constraint binding identities must align with terms")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class TrustedCompiledPricingConstraint(CompiledPricingConstraint):
    """Compiler-produced type-state; ordinary construction is never trusted."""

    @classmethod
    def _from_verified(
        cls, proposal: CompiledPricingConstraint, *, token: object
    ) -> "TrustedCompiledPricingConstraint":
        if token is not _CONSTRAINT_TRUST_TOKEN:
            raise DomainError("constraint trust may only be issued by the compiler")
        trusted = cls(
            schema_version=proposal.schema_version,
            constraint_id=proposal.constraint_id,
            certificate_id=proposal.certificate_id,
            certificate_schema_version=proposal.certificate_schema_version,
            certificate_validation_fingerprint=proposal.certificate_validation_fingerprint,
            relationship_type=proposal.relationship_type,
            terms=proposal.terms,
            relation=proposal.relation,
            bound=proposal.bound,
            certificate_provenance=proposal.certificate_provenance,
            binding_identities=proposal.binding_identities,
        )
        _record_trust(
            _TRUSTED_CONSTRAINTS,
            trusted,
            _content_commitment(constraint_identity_content(trusted)),
        )
        return trusted


def constraint_identity_content(constraint: CompiledPricingConstraint) -> dict[str, object]:
    """Return every material constraint field except its derived public ID."""

    return {
        "schema_version": constraint.schema_version,
        "certificate_id": constraint.certificate_id,
        "certificate_schema_version": constraint.certificate_schema_version,
        "certificate_validation_fingerprint": constraint.certificate_validation_fingerprint,
        "relationship_type": constraint.relationship_type,
        "terms": constraint.terms,
        "relation": constraint.relation,
        "bound": constraint.bound,
        "certificate_provenance": constraint.certificate_provenance,
        "binding_identities": constraint.binding_identities,
    }


def is_trusted_constraint(value: object) -> bool:
    if type(value) is not TrustedCompiledPricingConstraint:
        return False
    constraint = value
    entry = _registry_entry(_TRUSTED_CONSTRAINTS, constraint)
    if entry is None:
        return False
    try:
        commitment = _content_commitment(constraint_identity_content(constraint))
        return (
            commitment == entry.commitment
            and constraint.constraint_id.value == f"constraint:{commitment}"
        )
    except Exception:
        return False


class CompilationFailureCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    UNSUPPORTED_SCHEMA = "unsupported_schema_version"
    UNSUPPORTED_RELATIONSHIP = "unsupported_relationship_type"
    UNSUPPORTED_CONDITIONAL = "unsupported_conditional_relationship"
    UNSUPPORTED_SCALAR = "unsupported_scalar_or_non_binary_claim"
    MISSING_PROVENANCE = "missing_certificate_provenance"
    DUPLICATE_PROPOSITION = "duplicate_proposition_id"
    DUPLICATE_BINDING = "duplicate_binding_id"
    DUPLICATE_BINDING_PROPOSITION = "multiple_bindings_for_proposition"
    MISSING_BINDING = "missing_binding"
    UNKNOWN_BINDING_PROPOSITION = "binding_proposition_mismatch"
    DECLARATION_MISMATCH = "declaration_membership_mismatch"
    INVALID_CERTIFICATE = "invalid_certificate_structure"
    NO_FEASIBLE_STATES = "no_feasible_states"
    UNSUPPORTED_PAYOUT = "unsupported_payout"
    PAYOFF_VERIFICATION = "payoff_verification_failed"


@dataclass(frozen=True, slots=True)
class CompilationFailure:
    code: CompilationFailureCode
    message: str
    state_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompilationResult:
    constraint: TrustedCompiledPricingConstraint | None
    failures: tuple[CompilationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return self.constraint is not None and not self.failures

    @property
    def failure(self) -> CompilationFailure | None:
        return self.failures[0] if self.failures else None


class VerificationFailureCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    INVALID_CONSTRAINT = "invalid_constraint"
    NO_FEASIBLE_STATES = "no_feasible_states"
    MISSING_PAYOUT = "missing_payout_assignment"
    UNEXPECTED_PAYOUT = "unexpected_payout_assignment"
    UNSUPPORTED_PAYOUT = "unsupported_payout"
    UNKNOWN_BINDING = "unknown_binding"
    VIOLATION = "state_violates_constraint"


@dataclass(frozen=True, slots=True)
class VerificationFailure:
    code: VerificationFailureCode
    message: str
    state_id: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    valid: bool
    failures: tuple[VerificationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return self.valid and not self.failures


class ObservationFailureCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    WRONG_VENUE = "wrong_venue"
    MARKET_MISMATCH = "market_identity_mismatch"
    CONTRACT_MISMATCH = "contract_or_token_identity_mismatch"
    CLAIM_SIDE = "unknown_or_incompatible_claim_side"
    UNSUPPORTED_CONVENTION = "unsupported_price_convention"
    MISSING_BID = "missing_bid_side"
    MISSING_ASK = "missing_ask_side"
    CROSSED_INTERVAL = "crossed_interval"
    INVALID_PRICE = "invalid_price"
    INVALID_STATE = "invalid_replay_state"
    STALE = "stale_snapshot"
    MISSING_PROVENANCE = "missing_ordered_provenance"
    UNSUPPORTED_SCHEMA = "unsupported_schema_version"
    UNAVAILABLE_TIMESTAMP = "unavailable_timestamp"


@dataclass(frozen=True, slots=True)
class ObservationFailure:
    code: ObservationFailureCode
    message: str


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    schema_version: str
    observation_id: str
    proposition_id: PropositionId
    claim_binding_id: ClaimBindingId
    venue: Venue
    market: object
    contract: ContractReference | None
    native_claim_side: str | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    timestamp: datetime
    timestamp_source: str | None
    source_snapshot_schema_version: str
    source_price_convention: str | None
    validity: StateValidity
    raw_refs: tuple[RawReference, ...]
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVATION_SCHEMA_VERSION:
            raise DomainError("unsupported observation schema version")
        if not isinstance(self.observation_id, str) or not self.observation_id.startswith(
            "observation:"
        ):
            raise DomainError("observation_id must use the observation: prefix")
        if not isinstance(self.proposition_id, PropositionId):
            raise DomainError("observation proposition_id must be a PropositionId")
        if not isinstance(self.claim_binding_id, ClaimBindingId):
            raise DomainError("observation claim_binding_id must be a ClaimBindingId")
        if not isinstance(self.venue, Venue):
            raise DomainError("observation venue must be a Venue")
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise DomainError("observation timestamp must be timezone-aware")
        if not isinstance(self.validity, StateValidity):
            raise DomainError("observation validity must be StateValidity")
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("observation raw_refs must contain RawReference values")
        if self.timestamp_source is not None and not isinstance(self.timestamp_source, str):
            raise DomainError("observation timestamp_source must be a string when supplied")
        if not isinstance(self.source_snapshot_schema_version, str):
            raise DomainError("observation snapshot schema version must be a string")
        if self.source_price_convention is not None and not isinstance(
            self.source_price_convention, str
        ):
            raise DomainError("observation price convention must be a string when supplied")
        if self.native_claim_side is not None and not isinstance(self.native_claim_side, str):
            raise DomainError("observation claim side must be a string when supplied")
        if not isinstance(self.warnings, tuple):
            object.__setattr__(self, "warnings", tuple(self.warnings))
        if any(not isinstance(item, WarningRecord) for item in self.warnings):
            raise DomainError("observation warnings must contain WarningRecord values")
        if self.best_bid is not None:
            object.__setattr__(self, "best_bid", parse_price(self.best_bid, field="best_bid"))
        if self.best_ask is not None:
            object.__setattr__(self, "best_ask", parse_price(self.best_ask, field="best_ask"))


@dataclass(frozen=True, slots=True, weakref_slot=True)
class TrustedQuoteObservation(QuoteObservation):
    """Observation produced by a venue-native observation boundary."""

    @classmethod
    def _from_boundary(
        cls, observation: QuoteObservation, *, token: object
    ) -> "TrustedQuoteObservation":
        if token is not _OBSERVATION_TRUST_TOKEN:
            raise DomainError("observation trust may only be issued by the observation boundary")
        trusted = cls(
            schema_version=observation.schema_version,
            observation_id=observation.observation_id,
            proposition_id=observation.proposition_id,
            claim_binding_id=observation.claim_binding_id,
            venue=observation.venue,
            market=observation.market,
            contract=observation.contract,
            native_claim_side=observation.native_claim_side,
            best_bid=observation.best_bid,
            best_ask=observation.best_ask,
            timestamp=observation.timestamp,
            timestamp_source=observation.timestamp_source,
            source_snapshot_schema_version=observation.source_snapshot_schema_version,
            source_price_convention=observation.source_price_convention,
            validity=observation.validity,
            raw_refs=observation.raw_refs,
            warnings=observation.warnings,
        )
        _record_trust(
            _TRUSTED_OBSERVATIONS,
            trusted,
            _content_commitment(observation_identity_content(trusted)),
        )
        return trusted


def observation_identity_content(observation: QuoteObservation) -> dict[str, object]:
    return {
        "schema_version": observation.schema_version,
        "proposition_id": observation.proposition_id,
        "claim_binding_id": observation.claim_binding_id,
        "venue": observation.venue,
        "market": observation.market,
        "contract": observation.contract,
        "native_claim_side": observation.native_claim_side,
        "best_bid": observation.best_bid,
        "best_ask": observation.best_ask,
        "timestamp": observation.timestamp,
        "timestamp_source": observation.timestamp_source,
        "source_snapshot_schema_version": observation.source_snapshot_schema_version,
        "source_price_convention": observation.source_price_convention,
        "validity": observation.validity,
        "raw_refs": observation.raw_refs,
        "warnings": observation.warnings,
    }


def is_trusted_observation(value: object) -> bool:
    if type(value) is not TrustedQuoteObservation:
        return False
    observation = value
    entry = _registry_entry(_TRUSTED_OBSERVATIONS, observation)
    if entry is None:
        return False
    try:
        commitment = _content_commitment(observation_identity_content(observation))
        return (
            commitment == entry.commitment
            and observation.observation_id == f"observation:{commitment}"
        )
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class ObservationResult:
    observation: TrustedQuoteObservation | None
    failures: tuple[ObservationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return self.observation is not None and not self.failures

    @property
    def available(self) -> bool:
        return self.ok

    @property
    def failure(self) -> ObservationFailure | None:
        return self.failures[0] if self.failures else None


class ConstraintEvaluationStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    INDETERMINATE = "indeterminate"
    UNAVAILABLE = "unavailable"


class EvaluationFailureCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    INVALID_CONSTRAINT = "invalid_constraint"
    MISSING_OBSERVATION = "missing_observation"
    DUPLICATE_OBSERVATION = "duplicate_observation"
    UNEXPECTED_OBSERVATION = "unexpected_observation"
    IDENTITY_MISMATCH = "observation_identity_mismatch"
    INVALID_OBSERVATION = "invalid_observation"
    MISSING_PROVENANCE = "missing_observation_provenance"
    UNSYNCHRONIZED = "unsynchronized_observations"
    UNAVAILABLE_TIMESTAMP = "unavailable_timestamp"


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    code: EvaluationFailureCode
    message: str
    claim_binding_id: ClaimBindingId | None = None


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    schema_version: str
    evaluation_id: EvaluationId
    constraint_id: ConstraintId
    certificate_id: CertificateId
    status: ConstraintEvaluationStatus
    minimum_lhs: Decimal | None
    maximum_lhs: Decimal | None
    relation: ConstraintRelation
    bound: Decimal
    common_timestamp: datetime | None
    participating_observations: tuple[str, ...]
    participating_bindings: tuple[ClaimBindingId, ...]
    certificate_provenance: tuple[RawReference, ...]
    observation_provenance: tuple[RawReference, ...]
    combined_provenance: tuple[RawReference, ...]
    failures: tuple[EvaluationFailure, ...] = ()
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != EVALUATION_SCHEMA_VERSION:
            raise DomainError("unsupported evaluation schema version")
        if not isinstance(self.evaluation_id, EvaluationId):
            raise DomainError("evaluation_id must be an EvaluationId")
        if not isinstance(self.status, ConstraintEvaluationStatus):
            raise DomainError("evaluation status must be ConstraintEvaluationStatus")
        object.__setattr__(self, "bound", parse_decimal(self.bound, field="evaluation bound"))
        for field_name in ("minimum_lhs", "maximum_lhs"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, parse_decimal(value, field=field_name))
        if self.common_timestamp is not None and (
            self.common_timestamp.tzinfo is None or self.common_timestamp.utcoffset() is None
        ):
            raise DomainError("common_timestamp must be timezone-aware")
        for field_name in (
            "participating_observations",
            "participating_bindings",
            "certificate_provenance",
            "observation_provenance",
            "combined_provenance",
            "failures",
            "warnings",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluation: ConstraintEvaluation | None
    failures: tuple[EvaluationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return self.evaluation is not None and not self.failures

    @property
    def status(self) -> ConstraintEvaluationStatus:
        if self.evaluation is None:
            return ConstraintEvaluationStatus.UNAVAILABLE
        return self.evaluation.status


ConstraintIdentifier = ConstraintId
EvaluationIdentifier = EvaluationId
QuoteIntervalObservation = QuoteObservation
ConstraintStatus = ConstraintEvaluationStatus
EvaluationStatus = ConstraintEvaluationStatus


__all__ = [
    "CONSTRAINT_SCHEMA_VERSION",
    "OBSERVATION_SCHEMA_VERSION",
    "EVALUATION_SCHEMA_VERSION",
    "ConstraintId",
    "EvaluationId",
    "ConstraintRelation",
    "RelationOperator",
    "ConstraintRelationOperator",
    "ConstraintIdentifier",
    "EvaluationIdentifier",
    "LinearTerm",
    "ClaimBindingIdentity",
    "CompiledPricingConstraint",
    "TrustedCompiledPricingConstraint",
    "is_trusted_constraint",
    "CompilationFailureCode",
    "CompilationFailure",
    "CompilationResult",
    "VerificationFailureCode",
    "VerificationFailure",
    "VerificationResult",
    "ObservationFailureCode",
    "ObservationFailure",
    "QuoteObservation",
    "TrustedQuoteObservation",
    "observation_identity_content",
    "is_trusted_observation",
    "ObservationResult",
    "ConstraintEvaluationStatus",
    "EvaluationFailureCode",
    "EvaluationFailure",
    "ConstraintEvaluation",
    "EvaluationResult",
    "QuoteIntervalObservation",
    "ConstraintStatus",
    "EvaluationStatus",
]
