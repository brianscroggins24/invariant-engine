"""Bounded evidence, provenance, completeness, and semantic review records."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference
from invariant_engine.relationships.ids import EvidenceId, SemanticReviewId


class EvidenceKind(StrEnum):
    MARKET_RULE = "market_rule"
    RESOLUTION_SOURCE = "resolution_source"
    FIXTURE_NOTE = "fixture_note"
    OTHER = "other"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


def _nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} must be non-empty")
    return value


def _tuple_strings(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        values = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise DomainError(f"{field} must contain non-empty strings")
    return values


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: EvidenceId
    kind: EvidenceKind
    rule_text: str | None = None
    evidence_span: str | None = None
    locator: str | None = None
    content_digest: str | None = None
    raw_refs: tuple[RawReference, ...] = ()
    assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    edge_cases: tuple[str, ...] = ()
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, EvidenceId):
            raise DomainError("evidence_id must be an EvidenceId")
        if not isinstance(self.kind, EvidenceKind):
            raise DomainError("evidence kind must be an EvidenceKind")
        if self.rule_text is None and self.evidence_span is None:
            raise DomainError("evidence requires rule_text or evidence_span")
        for field, value in (("rule_text", self.rule_text), ("evidence_span", self.evidence_span)):
            if value is not None:
                _nonempty(value, field)
        if self.locator is not None:
            _nonempty(self.locator, "locator")
        if self.content_digest is not None:
            _nonempty(self.content_digest, "content_digest")
        if not isinstance(self.synthetic, bool):
            raise DomainError("synthetic must be boolean")
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("evidence raw_refs must contain RawReference values")
        for field in ("assumptions", "uncertainties", "edge_cases"):
            object.__setattr__(self, field, _tuple_strings(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class CompletenessDeclaration:
    declared_complete: bool
    basis: str
    attestation_scope: str
    evidence_ids: tuple[EvidenceId, ...] = ()
    raw_refs: tuple[RawReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.declared_complete, bool):
            raise DomainError("declared_complete must be boolean")
        _nonempty(self.basis, "completeness basis")
        _nonempty(self.attestation_scope, "completeness attestation_scope")
        for field in ("evidence_ids", "raw_refs"):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if any(not isinstance(item, EvidenceId) for item in self.evidence_ids):
            raise DomainError("completeness evidence_ids must contain EvidenceId values")
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("completeness raw_refs must contain RawReference values")


@dataclass(frozen=True, slots=True)
class SemanticReview:
    review_id: SemanticReviewId
    reviewer: str
    decision: ReviewDecision
    reviewed_at: datetime
    basis: str
    authority_scope: str
    draft_fingerprint: str
    fingerprint_algorithm: str = "sha256/stable-json-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.review_id, SemanticReviewId):
            raise DomainError("review_id must be a SemanticReviewId")
        _nonempty(self.reviewer, "reviewer")
        if not isinstance(self.decision, ReviewDecision):
            raise DomainError("decision must be a ReviewDecision")
        if not isinstance(self.reviewed_at, datetime):
            raise DomainError("reviewed_at must be a datetime")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise DomainError("reviewed_at must be timezone-aware")
        _nonempty(self.basis, "review basis")
        _nonempty(self.authority_scope, "authority_scope")
        _nonempty(self.fingerprint_algorithm, "fingerprint_algorithm")
        if not isinstance(self.draft_fingerprint, str) or len(self.draft_fingerprint) != 64:
            raise DomainError("draft_fingerprint must be a SHA-256 hexadecimal digest")
        try:
            int(self.draft_fingerprint, 16)
        except ValueError as exc:
            raise DomainError("draft_fingerprint must be hexadecimal") from exc

    @classmethod
    def for_draft(
        cls,
        draft: Any,
        *,
        review_id: SemanticReviewId,
        reviewer: str,
        decision: ReviewDecision,
        reviewed_at: datetime,
        basis: str,
        authority_scope: str,
    ) -> "SemanticReview":
        from invariant_engine.relationships.certificates import reviewable_fingerprint

        return cls(
            review_id=review_id,
            reviewer=reviewer,
            decision=decision,
            reviewed_at=reviewed_at,
            basis=basis,
            authority_scope=authority_scope,
            draft_fingerprint=reviewable_fingerprint(draft),
        )


RelationshipEvidence = Evidence
EvidenceRecord = Evidence
StateSpaceCompleteness = CompletenessDeclaration
SemanticReviewAttestation = SemanticReview

__all__ = [
    "CompletenessDeclaration",
    "Evidence",
    "EvidenceRecord",
    "EvidenceKind",
    "RelationshipEvidence",
    "ReviewDecision",
    "SemanticReview",
    "SemanticReviewAttestation",
    "StateSpaceCompleteness",
]
