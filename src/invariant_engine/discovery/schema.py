"""Immutable, provider-neutral records used by recorded discovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.relationships.propositions import Threshold
from invariant_engine.serialization import stable_json_bytes

DISCOVERY_INPUT_SCHEMA_VERSION = "discovery-input-v1"
DISCOVERY_OUTPUT_SCHEMA_VERSION = "discovery-output-v1"
DISCOVERY_FIXTURE_SCHEMA_VERSION = "discovery-fixture-v1"
DISCOVERY_EVALUATION_LABELS_VERSION = "discovery-evaluation-labels-v1"


class DiscoveryOutcome(StrEnum):
    PROPOSALS = "proposals"
    ABSTAIN = "abstain"
    REJECT = "reject"


class DiscoveryDisposition(StrEnum):
    DISABLED = "disabled"
    PROPOSALS = "proposals"
    ABSTAINED = "abstained"
    REJECTED = "rejected"
    RETRY_EXHAUSTED = "retry_exhausted"


class PrefilterName(StrEnum):
    TOPIC = "topic"
    ENTITY = "entity"
    DATE = "date"
    THRESHOLD = "threshold"
    UNIT = "unit"


class PrefilterStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} must be a non-empty string")
    return value


def _tuple_strings(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        values = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise DomainError(f"{field} must contain non-empty strings")
    return values


@dataclass(frozen=True, slots=True)
class PolymarketDiscoveryIdentity:
    market_reference: str
    outcome_token_reference: str
    native_outcome_side: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.market_reference, "Polymarket market_reference")
        _nonempty(self.outcome_token_reference, "Polymarket outcome_token_reference")
        if self.native_outcome_side is not None:
            side = _nonempty(self.native_outcome_side, "Polymarket native_outcome_side")
            if side not in {"yes", "no"}:
                raise DomainError("unsupported Polymarket native_outcome_side")


@dataclass(frozen=True, slots=True)
class KalshiDiscoveryIdentity:
    market_ticker: str
    market_id: str
    native_side: str

    def __post_init__(self) -> None:
        _nonempty(self.market_ticker, "Kalshi market_ticker")
        _nonempty(self.market_id, "Kalshi market_id")
        if self.native_side not in {"yes", "no"}:
            raise DomainError("Kalshi native_side must be yes or no")


VenueDiscoveryIdentity = PolymarketDiscoveryIdentity | KalshiDiscoveryIdentity


@dataclass(frozen=True, slots=True)
class DiscoveryRuleInput:
    rule_input_id: str
    rule_text: str
    raw_refs: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        _nonempty(self.rule_input_id, "rule_input_id")
        _nonempty(self.rule_text, "rule_text")
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if not self.raw_refs:
            raise DomainError("rule raw_refs must not be empty")
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("rule raw_refs must contain RawReference values")


@dataclass(frozen=True, slots=True)
class DiscoveryThreshold:
    name: str
    comparator: str
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        _nonempty(self.name, "threshold name")
        if self.comparator not in {"<", "<=", "=", ">=", ">"}:
            raise DomainError("threshold comparator is unsupported")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise DomainError("threshold value must be a finite Decimal")
        _nonempty(self.unit, "threshold unit")

    def to_relationship_threshold(self) -> Threshold:
        return Threshold(self.name, self.value, self.unit)


@dataclass(frozen=True, slots=True)
class DiscoverySimilarity:
    value: Decimal
    label: str | None = None
    provider: str | None = None
    version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise DomainError("similarity value must be a finite Decimal")
        for field in ("label", "provider", "version"):
            value = getattr(self, field)
            if value is not None:
                _nonempty(value, f"similarity {field}")


@dataclass(frozen=True, slots=True)
class DiscoveryInput:
    input_id: str
    venue: Venue
    venue_identity: VenueDiscoveryIdentity
    claim_classification: str
    question: str
    market_rules: tuple[DiscoveryRuleInput, ...]
    raw_refs: tuple[RawReference, ...]
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    end_date: date | None = None
    thresholds: tuple[DiscoveryThreshold, ...] = ()
    unit: str | None = None
    similarity: DiscoverySimilarity | None = None

    def __post_init__(self) -> None:
        _nonempty(self.input_id, "discovery input_id")
        if not isinstance(self.venue, Venue):
            raise DomainError("discovery venue must be a Venue")
        if self.venue is Venue.POLYMARKET and not isinstance(
            self.venue_identity, PolymarketDiscoveryIdentity
        ):
            raise DomainError("Polymarket input requires a Polymarket identity")
        if self.venue is Venue.KALSHI and not isinstance(
            self.venue_identity, KalshiDiscoveryIdentity
        ):
            raise DomainError("Kalshi input requires a Kalshi identity")
        if self.claim_classification not in {"binary_unit", "scalar", "conditional"}:
            raise DomainError("unsupported discovery claim classification")
        _nonempty(self.question, "discovery question")
        for field in ("market_rules", "raw_refs", "topics", "entities", "thresholds"):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if any(not isinstance(item, DiscoveryRuleInput) for item in self.market_rules):
            raise DomainError("market_rules must contain DiscoveryRuleInput values")
        if any(raw.venue is not self.venue for rule in self.market_rules for raw in rule.raw_refs):
            raise DomainError("market rule raw_refs must be native to the input venue")
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("discovery raw_refs must contain RawReference values")
        if not self.raw_refs:
            raise DomainError("discovery raw_refs must not be empty")
        if any(not isinstance(item, DiscoveryThreshold) for item in self.thresholds):
            raise DomainError("thresholds must contain DiscoveryThreshold values")
        _tuple_strings(self.topics, "topics")
        _tuple_strings(self.entities, "entities")
        if self.unit is not None:
            _nonempty(self.unit, "unit")
        if any(raw.venue is not self.venue for raw in self.raw_refs):
            raise DomainError("input raw_refs must be native to the input venue")


@dataclass(frozen=True, slots=True)
class DiscoveryRequest:
    inputs: tuple[DiscoveryInput, ...]
    schema_version: str = DISCOVERY_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DISCOVERY_INPUT_SCHEMA_VERSION:
            raise DomainError("unsupported discovery input schema version")
        if not isinstance(self.inputs, tuple):
            object.__setattr__(self, "inputs", tuple(self.inputs))
        if not self.inputs or any(not isinstance(item, DiscoveryInput) for item in self.inputs):
            raise DomainError("discovery request requires input records")
        input_ids = tuple(item.input_id for item in self.inputs)
        if len(input_ids) != len(set(input_ids)):
            raise DomainError("discovery input IDs must be unique")

    def to_bytes(self) -> bytes:
        return stable_json_bytes({"schema_version": self.schema_version, "inputs": self.inputs})

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PrefilterPolicy:
    required_signals: tuple[PrefilterName, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.required_signals, tuple):
            object.__setattr__(self, "required_signals", tuple(self.required_signals))
        if any(not isinstance(item, PrefilterName) for item in self.required_signals):
            raise DomainError("prefilter policy must contain PrefilterName values")
        if len(self.required_signals) != len(set(self.required_signals)):
            raise DomainError("prefilter policy signals must be unique")


@dataclass(frozen=True, slots=True)
class PrefilterSignal:
    name: PrefilterName
    status: PrefilterStatus
    reason: str
    left_value: str | None = None
    right_value: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, PrefilterName) or not isinstance(self.status, PrefilterStatus):
            raise DomainError("prefilter signal has an invalid bounded value")
        _nonempty(self.reason, "prefilter reason")


@dataclass(frozen=True, slots=True)
class PrefilterEvaluation:
    left_input_id: str
    right_input_id: str
    signals: tuple[PrefilterSignal, ...]
    required_passed: bool

    def __post_init__(self) -> None:
        _nonempty(self.left_input_id, "left_input_id")
        _nonempty(self.right_input_id, "right_input_id")
        if not isinstance(self.signals, tuple):
            object.__setattr__(self, "signals", tuple(self.signals))
        if any(not isinstance(item, PrefilterSignal) for item in self.signals):
            raise DomainError("prefilter signals must contain PrefilterSignal values")


@dataclass(frozen=True, slots=True)
class EvidenceSpanProposal:
    rule_input_id: str
    start: int
    end: int
    text: str
    raw_refs: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        _nonempty(self.rule_input_id, "evidence rule_input_id")
        if not isinstance(self.start, int) or isinstance(self.start, bool):
            raise DomainError("evidence start must be an integer")
        if not isinstance(self.end, int) or isinstance(self.end, bool):
            raise DomainError("evidence end must be an integer")
        if self.start < 0 or self.start >= self.end:
            raise DomainError("evidence span must be non-empty and non-negative")
        _nonempty(self.text, "evidence span text")
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("evidence span raw_refs must contain RawReference values")


@dataclass(frozen=True, slots=True)
class PropositionProposal:
    proposal_proposition_id: str
    input_id: str
    binding_ref: str

    def __post_init__(self) -> None:
        _nonempty(self.proposal_proposition_id, "proposal proposition ID")
        _nonempty(self.input_id, "proposal input_id")
        _nonempty(self.binding_ref, "proposal binding_ref")


@dataclass(frozen=True, slots=True)
class DiscoveryProposal:
    proposal_id: str
    relationship_type: str
    propositions: tuple[PropositionProposal, ...]
    claim_classification: str
    evidence_spans: tuple[EvidenceSpanProposal, ...]
    assumptions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    edge_cases: tuple[str, ...]
    event_scope: str | None = None
    thresholds: tuple[DiscoveryThreshold, ...] = ()
    condition: str | None = None
    close_time: str | None = None
    resolution_time: str | None = None
    resolution_sources: tuple[str, ...] = ()
    cancellation_behavior: str | None = None
    void_behavior: str | None = None
    refund_behavior: str | None = None
    payout_structure: str | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    unit: str | None = None
    timing: str | None = None
    resolution: str | None = None
    conflicting_evidence: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.proposal_id, "proposal_id")
        _nonempty(self.relationship_type, "relationship_type")
        if not isinstance(self.propositions, tuple):
            object.__setattr__(self, "propositions", tuple(self.propositions))
        if not isinstance(self.evidence_spans, tuple):
            object.__setattr__(self, "evidence_spans", tuple(self.evidence_spans))
        if any(not isinstance(item, PropositionProposal) for item in self.propositions):
            raise DomainError("proposal propositions have an invalid structure")
        if any(not isinstance(item, EvidenceSpanProposal) for item in self.evidence_spans):
            raise DomainError("proposal evidence spans have an invalid structure")
        if self.claim_classification not in {"binary_unit", "scalar", "conditional"}:
            raise DomainError("unsupported proposal claim classification")
        if not isinstance(self.conflicting_evidence, bool):
            raise DomainError("conflicting_evidence must be boolean")
        for field in ("assumptions", "uncertainties", "edge_cases", "resolution_sources"):
            object.__setattr__(self, field, _tuple_strings(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class ParsedDiscoveryOutput:
    outcome: DiscoveryOutcome
    proposals: tuple[DiscoveryProposal, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DiscoveryOutcome):
            raise DomainError("output outcome must be a DiscoveryOutcome")
        if not isinstance(self.proposals, tuple):
            object.__setattr__(self, "proposals", tuple(self.proposals))
        if any(not isinstance(item, DiscoveryProposal) for item in self.proposals):
            raise DomainError("parsed proposals have an invalid structure")
        if self.outcome is DiscoveryOutcome.PROPOSALS and not self.proposals:
            raise DomainError("proposal outcome requires at least one proposal")
        if self.outcome is not DiscoveryOutcome.PROPOSALS:
            if self.proposals:
                raise DomainError("terminal abstain/reject output cannot contain proposals")
            _nonempty(self.reason, "terminal output reason")


__all__ = [
    "DISCOVERY_EVALUATION_LABELS_VERSION",
    "DISCOVERY_FIXTURE_SCHEMA_VERSION",
    "DISCOVERY_INPUT_SCHEMA_VERSION",
    "DISCOVERY_OUTPUT_SCHEMA_VERSION",
    "DiscoveryDisposition",
    "DiscoveryInput",
    "DiscoveryProposal",
    "DiscoveryOutcome",
    "EvidenceSpanProposal",
    "ParsedDiscoveryOutput",
    "PropositionProposal",
    "DiscoveryRequest",
    "DiscoveryRuleInput",
    "DiscoverySimilarity",
    "DiscoveryThreshold",
    "KalshiDiscoveryIdentity",
    "PolymarketDiscoveryIdentity",
    "PrefilterEvaluation",
    "PrefilterName",
    "PrefilterPolicy",
    "PrefilterSignal",
    "PrefilterStatus",
]
