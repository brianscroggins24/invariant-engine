"""Validated relationship certificates and their review fingerprint."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from invariant_engine.domain.ids import RawReference
from invariant_engine.relationships.candidates import (
    RelationshipCertificateDraft,
    RelationshipDeclaration,
)
from invariant_engine.relationships.claims import ClaimBinding
from invariant_engine.relationships.evidence import (
    CompletenessDeclaration,
    Evidence,
    SemanticReview,
)
from invariant_engine.relationships.ids import CandidateId, CertificateId, DraftId, EvidenceId
from invariant_engine.relationships.propositions import ObservationPeriod, Proposition, Threshold
from invariant_engine.relationships.states import FeasibleState
from invariant_engine.serialization import stable_json_bytes

RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION = "relationship-certificate-v1"


def reviewable_content(draft: RelationshipCertificateDraft) -> dict[str, object]:
    """Return the exact draft content covered by a semantic review."""

    return {
        "draft_id": draft.draft_id,
        "originating_candidate_id": draft.originating_candidate_id,
        "schema_version": draft.schema_version,
        "propositions": draft.propositions,
        "bindings": draft.bindings,
        "proposed_relationship": draft.proposed_relationship,
        "evidence": draft.evidence,
        "event_scope": draft.event_scope,
        "thresholds": draft.thresholds,
        "observation_period": draft.observation_period,
        "close_time": draft.close_time,
        "resolution_time": draft.resolution_time,
        "resolution_sources": draft.resolution_sources,
        "cancellation_behavior": draft.cancellation_behavior,
        "void_behavior": draft.void_behavior,
        "refund_behavior": draft.refund_behavior,
        "payout_structure": draft.payout_structure,
        "edge_cases": draft.edge_cases,
        "assumptions": draft.assumptions,
        "uncertainties": draft.uncertainties,
        "evidence_provenance": draft.evidence_provenance,
        "validation_method": draft.validation_method,
        "feasible_states": draft.feasible_states,
        "completeness": draft.completeness,
    }


def reviewable_fingerprint(draft: RelationshipCertificateDraft) -> str:
    return hashlib.sha256(stable_json_bytes(reviewable_content(draft))).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class RelationshipCertificate:
    """A successful deterministic validation result.

    The class has no public initializing constructor. The validator constructs
    it directly in the successful terminal branch of deterministic validation.
    """

    certificate_id: CertificateId
    originating_candidate_id: CandidateId
    source_draft_id: DraftId
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
    feasible_states: tuple[FeasibleState, ...]
    completeness: CompletenessDeclaration
    semantic_review: SemanticReview
    validation_method: str
    validation_fingerprint: str
    schema_version: str

    def __init__(self) -> None:
        raise TypeError("RelationshipCertificate must be produced by validate_draft")


__all__ = [
    "RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION",
    "RelationshipCertificate",
    "reviewable_content",
    "reviewable_fingerprint",
]
