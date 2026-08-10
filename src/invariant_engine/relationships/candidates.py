"""Untrusted relationship hypotheses and certificate drafts."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference
from invariant_engine.relationships.claims import (
    ClaimBinding,
    KalshiClaimBinding,
    PolymarketClaimBinding,
)
from invariant_engine.relationships.evidence import (
    CompletenessDeclaration,
    Evidence,
    SemanticReview,
)
from invariant_engine.relationships.ids import CandidateId, DraftId, EvidenceId, PropositionId
from invariant_engine.relationships.propositions import ObservationPeriod, Proposition, Threshold
from invariant_engine.relationships.states import FeasibleState


class RelationshipType(StrEnum):
    IMPLICATION = "implication"
    EQUIVALENCE = "equivalence"
    COMPLEMENT = "complement"
    SUBSET = "subset"
    SUPERSET = "superset"
    MUTUALLY_EXCLUSIVE_SET = "mutually_exclusive_set"
    EXHAUSTIVE_SET = "exhaustive_set"
    EXCLUSIVE_AND_EXHAUSTIVE_PARTITION = "exclusive_and_exhaustive_partition"
    CONDITIONAL = "conditional"
    MUTUALLY_EXCLUSIVE = "mutually_exclusive_set"
    EXHAUSTIVE = "exhaustive_set"
    PARTITION = "exclusive_and_exhaustive_partition"


@dataclass(frozen=True, slots=True)
class RelationshipDeclaration:
    relationship_type: RelationshipType
    proposition_ids: tuple[PropositionId, ...]
    condition: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.relationship_type, RelationshipType):
            raise DomainError("relationship_type must be a RelationshipType")
        if not isinstance(self.proposition_ids, tuple):
            object.__setattr__(self, "proposition_ids", tuple(self.proposition_ids))
        if any(not isinstance(item, PropositionId) for item in self.proposition_ids):
            raise DomainError("relationship proposition_ids must contain PropositionId values")
        if self.relationship_type in {
            RelationshipType.MUTUALLY_EXCLUSIVE_SET,
            RelationshipType.EXHAUSTIVE_SET,
            RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
        }:
            object.__setattr__(
                self,
                "proposition_ids",
                tuple(sorted(self.proposition_ids, key=lambda item: item.value)),
            )
        if self.condition is not None and (
            not isinstance(self.condition, str) or not self.condition.strip()
        ):
            raise DomainError("relationship condition must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class RelationshipCandidate:
    """An explicitly untrusted hypothesis; it has no validation state or action API."""

    candidate_id: CandidateId
    proposition_ids: tuple[PropositionId, ...]
    proposed_relationship: RelationshipDeclaration
    evidence_ids: tuple[EvidenceId, ...] = ()
    raw_refs: tuple[RawReference, ...] = ()
    source: str = "manual"

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, CandidateId):
            raise DomainError("candidate_id must be a CandidateId")
        if not isinstance(self.proposition_ids, tuple):
            object.__setattr__(self, "proposition_ids", tuple(self.proposition_ids))
        if not isinstance(self.evidence_ids, tuple):
            object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if any(not isinstance(item, PropositionId) for item in self.proposition_ids):
            raise DomainError("candidate proposition_ids must contain PropositionId values")
        if not isinstance(self.proposed_relationship, RelationshipDeclaration):
            raise DomainError("proposed_relationship must be a RelationshipDeclaration")
        if tuple(self.proposed_relationship.proposition_ids) != self.proposition_ids:
            raise DomainError("candidate proposition_ids must match its declaration")
        if any(not isinstance(item, EvidenceId) for item in self.evidence_ids):
            raise DomainError("candidate evidence_ids must contain EvidenceId values")
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("candidate raw_refs must contain RawReference values")
        if not isinstance(self.source, str) or not self.source.strip():
            raise DomainError("candidate source must be non-empty")
        if self.source not in {"manual", "synthetic", "fixture"}:
            raise DomainError("Milestone 2.1 candidate source must be manual or synthetic")


@dataclass(frozen=True, slots=True)
class RelationshipCertificateDraft:
    """Reviewable, not-yet-validated relationship material."""

    draft_id: DraftId
    originating_candidate_id: CandidateId
    propositions: tuple[Proposition, ...]
    bindings: tuple[ClaimBinding, ...]
    proposed_relationship: RelationshipDeclaration
    evidence: tuple[Evidence, ...]
    event_scope: str | None
    thresholds: tuple[Threshold, ...]
    observation_period: ObservationPeriod | None
    close_time: datetime | None
    resolution_time: datetime | None
    resolution_sources: tuple[EvidenceId, ...]
    cancellation_behavior: str | None
    void_behavior: str | None
    refund_behavior: str | None
    payout_structure: str | None
    edge_cases: tuple[str, ...]
    assumptions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence_provenance: tuple[RawReference, ...]
    validation_method: str
    feasible_states: tuple[FeasibleState, ...]
    completeness: CompletenessDeclaration
    semantic_review: SemanticReview | None = None
    schema_version: str = "relationship-draft-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.draft_id, DraftId):
            raise DomainError("draft_id must be a DraftId")
        if not isinstance(self.originating_candidate_id, CandidateId):
            raise DomainError("originating_candidate_id must be a CandidateId")
        if not isinstance(self.propositions, tuple):
            object.__setattr__(self, "propositions", tuple(self.propositions))
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        if not isinstance(self.evidence, tuple):
            object.__setattr__(self, "evidence", tuple(self.evidence))
        if not isinstance(self.feasible_states, tuple):
            object.__setattr__(self, "feasible_states", tuple(self.feasible_states))
        if any(not isinstance(item, Proposition) for item in self.propositions):
            raise DomainError("draft propositions must contain Proposition values")
        if any(
            not isinstance(item, (PolymarketClaimBinding, KalshiClaimBinding))
            for item in self.bindings
        ):
            raise DomainError("draft bindings must be claim bindings")
        if any(not isinstance(item, Evidence) for item in self.evidence):
            raise DomainError("draft evidence must contain Evidence values")
        if any(not isinstance(item, FeasibleState) for item in self.feasible_states):
            raise DomainError("draft feasible_states must contain FeasibleState values")
        if not isinstance(self.proposed_relationship, RelationshipDeclaration):
            raise DomainError("draft proposed_relationship must be a RelationshipDeclaration")
        if not isinstance(self.completeness, CompletenessDeclaration):
            raise DomainError("draft completeness must be a CompletenessDeclaration")
        if self.semantic_review is not None and not isinstance(
            self.semantic_review, SemanticReview
        ):
            raise DomainError("semantic_review must be a SemanticReview when supplied")
        if self.observation_period is not None and not isinstance(
            self.observation_period, ObservationPeriod
        ):
            raise DomainError("observation_period must be an ObservationPeriod when supplied")
        if self.proposed_relationship.relationship_type in {
            RelationshipType.MUTUALLY_EXCLUSIVE_SET,
            RelationshipType.EXHAUSTIVE_SET,
            RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
        }:
            object.__setattr__(
                self,
                "propositions",
                tuple(sorted(self.propositions, key=lambda item: item.proposition_id.value)),
            )
        object.__setattr__(
            self,
            "bindings",
            tuple(sorted(self.bindings, key=lambda item: item.binding_id.value)),
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted(self.evidence, key=lambda item: item.evidence_id.value)),
        )
        object.__setattr__(
            self,
            "feasible_states",
            tuple(sorted(self.feasible_states, key=lambda item: item.state_id.value)),
        )
        for field in ("thresholds", "resolution_sources", "evidence_provenance"):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if any(not isinstance(item, Threshold) for item in self.thresholds):
            raise DomainError("thresholds must contain Threshold values")
        if self.close_time is not None:
            _aware(self.close_time, "close_time")
        if self.resolution_time is not None:
            _aware(self.resolution_time, "resolution_time")
        if self.close_time is not None and self.resolution_time is not None:
            if self.resolution_time < self.close_time:
                raise DomainError("resolution_time must not precede close_time")
        for field in ("validation_method", "schema_version"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(f"{field} must be non-empty")
        for field in (
            "event_scope",
            "cancellation_behavior",
            "void_behavior",
            "refund_behavior",
            "payout_structure",
        ):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise DomainError(f"{field} must be non-empty when supplied")
        for field in ("edge_cases", "assumptions", "uncertainties"):
            values = tuple(getattr(self, field))
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise DomainError(f"{field} must contain non-empty strings")
            object.__setattr__(self, field, values)
        if any(not isinstance(item, EvidenceId) for item in self.resolution_sources):
            raise DomainError("resolution_sources must contain EvidenceId values")
        if any(not isinstance(item, RawReference) for item in self.evidence_provenance):
            raise DomainError("evidence_provenance must contain RawReference values")

    def with_semantic_review(self, review: SemanticReview) -> "RelationshipCertificateDraft":
        if not isinstance(review, SemanticReview):
            raise DomainError("review must be a SemanticReview")
        return replace(self, semantic_review=review)


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f"{field} must be timezone-aware")


__all__ = [
    "RelationshipKind",
    "RelationshipCandidate",
    "RelationshipCertificateDraft",
    "RelationshipDeclaration",
    "RelationshipType",
]

RelationshipKind = RelationshipType
