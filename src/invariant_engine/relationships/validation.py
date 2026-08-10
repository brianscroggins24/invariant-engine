"""Stable, fail-closed deterministic validation of relationship drafts."""

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from invariant_engine.domain.decimal_policy import ONE, ZERO
from invariant_engine.domain.ids import RawReference
from invariant_engine.relationships.candidates import (
    RelationshipCertificateDraft,
    RelationshipDeclaration,
    RelationshipType,
)
from invariant_engine.relationships.certificates import (
    RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION,
    RelationshipCertificate,
    reviewable_content,
    reviewable_fingerprint,
)
from invariant_engine.relationships.claims import (
    ClaimClassification,
)
from invariant_engine.relationships.evidence import ReviewDecision
from invariant_engine.relationships.ids import CertificateId
from invariant_engine.relationships.states import FeasibleState
from invariant_engine.serialization import stable_json_bytes

SUPPORTED_DRAFT_SCHEMA_VERSION = "relationship-draft-v1"
SUPPORTED_VALIDATION_METHOD = "truth-payoff-exhaustive-supplied-v1"
SUPPORTED_REVIEW_FINGERPRINT_ALGORITHM = "sha256/stable-json-v1"


class ValidationFailureCode(StrEnum):
    WRONG_TYPE = "wrong_type"
    MISSING_REVIEW = "missing_review"
    REJECTED_REVIEW = "rejected_review"
    REVIEW_FINGERPRINT_MISMATCH = "review_fingerprint_mismatch"
    INCOMPLETE_STATE_SPACE = "incomplete_state_space"
    UNSUPPORTED_CONDITIONAL = "unsupported_conditional_relationship"
    UNSUPPORTED_SCALAR = "unsupported_scalar_or_non_binary_claim"
    INVALID_ARITY = "invalid_arity_or_membership"
    INCOMPLETE_TRUTH = "incomplete_or_duplicate_truth_assignments"
    INCOMPLETE_PAYOUT = "incomplete_or_duplicate_payout_assignments"
    INVALID_PAYOUT = "non_unit_or_inconsistent_payout"
    MISSING_PROVENANCE = "missing_required_provenance"
    INVALID_EVIDENCE_REFERENCES = "invalid_evidence_references"
    UNSUPPORTED_METADATA = "unsupported_metadata"
    COUNTEREXAMPLE = "relationship_counterexample"


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    code: ValidationFailureCode
    message: str
    state_id: object | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    certificate: RelationshipCertificate | None
    failures: tuple[ValidationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return self.certificate is not None and not self.failures

    @property
    def is_valid(self) -> bool:
        return self.ok

    @property
    def failure(self) -> ValidationFailure | None:
        return self.failures[0] if self.failures else None


def _failure(
    code: ValidationFailureCode, message: str, state_id: object | None = None
) -> ValidationResult:
    return ValidationResult(None, (ValidationFailure(code, message, state_id),))


def _unique(values: tuple[object, ...]) -> bool:
    return len(values) == len(set(values))


def _reference_ids_are_unique(values: tuple[object, ...]) -> bool:
    return _unique(values)


def _evidence_references_are_closed(draft: RelationshipCertificateDraft) -> bool:
    evidence_ids = tuple(evidence.evidence_id for evidence in draft.evidence)
    if not _reference_ids_are_unique(evidence_ids):
        return False
    evidence_set = set(evidence_ids)
    reference_groups: list[tuple[object, ...]] = [
        draft.resolution_sources,
        draft.completeness.evidence_ids,
    ]
    for binding in draft.bindings:
        reference_groups.append(binding.evidence_ids)
    for state in draft.feasible_states:
        reference_groups.append(state.evidence_ids)
    if any(not _reference_ids_are_unique(group) for group in reference_groups):
        return False
    references = [reference for group in reference_groups for reference in group]
    return all(reference in evidence_set for reference in references)


def _raw_provenance_is_closed(draft: RelationshipCertificateDraft) -> bool:
    if not draft.evidence_provenance or not draft.evidence:
        return False
    top_level = draft.evidence_provenance
    if not _reference_ids_are_unique(top_level):
        return False
    nested: list[RawReference] = []
    nested.extend(draft.completeness.raw_refs)
    nested.extend(draft.evidence_provenance)
    for evidence in draft.evidence:
        nested.extend(evidence.raw_refs)
    for binding in draft.bindings:
        nested.extend(binding.raw_refs)
    for state in draft.feasible_states:
        nested.extend(state.raw_refs)
    if any(reference not in top_level for reference in nested):
        return False
    if any(not evidence.locator and not evidence.raw_refs for evidence in draft.evidence):
        return False
    return True


def _critical_provenance_is_present(draft: RelationshipCertificateDraft) -> bool:
    if not draft.completeness.evidence_ids and not draft.completeness.raw_refs:
        return False
    if any(not binding.evidence_ids and not binding.raw_refs for binding in draft.bindings):
        return False
    if any(not state.evidence_ids and not state.raw_refs for state in draft.feasible_states):
        return False
    return True


def _arity(declaration: RelationshipDeclaration) -> bool:
    count = len(declaration.proposition_ids)
    if declaration.relationship_type in {
        RelationshipType.IMPLICATION,
        RelationshipType.EQUIVALENCE,
        RelationshipType.COMPLEMENT,
        RelationshipType.SUBSET,
        RelationshipType.SUPERSET,
    }:
        return count == 2 and _unique(declaration.proposition_ids)
    if declaration.relationship_type in {
        RelationshipType.MUTUALLY_EXCLUSIVE_SET,
        RelationshipType.EXHAUSTIVE_SET,
        RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
    }:
        return count >= 2 and _unique(declaration.proposition_ids)
    return True


def _relationship_holds(draft: RelationshipCertificateDraft, state: FeasibleState) -> bool:
    relationship = draft.proposed_relationship
    truth = state.truth_assignments
    values = [truth[item] for item in relationship.proposition_ids]
    if relationship.relationship_type in {RelationshipType.IMPLICATION, RelationshipType.SUBSET}:
        return not values[0] or values[1]
    if relationship.relationship_type is RelationshipType.SUPERSET:
        return not values[1] or values[0]
    if relationship.relationship_type is RelationshipType.EQUIVALENCE:
        return values[0] == values[1]
    if relationship.relationship_type is RelationshipType.COMPLEMENT:
        return sum(values) == 1
    true_count = sum(values)
    if relationship.relationship_type is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        return true_count <= 1
    if relationship.relationship_type is RelationshipType.EXHAUSTIVE_SET:
        return true_count >= 1
    if relationship.relationship_type is RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION:
        return true_count == 1
    return False


def validate_draft(value: object) -> ValidationResult:
    """Validate one draft in a fixed order and never accept a candidate."""

    if not isinstance(value, RelationshipCertificateDraft):
        return _failure(
            ValidationFailureCode.WRONG_TYPE,
            "validator requires a RelationshipCertificateDraft",
        )
    draft = value
    review = draft.semantic_review
    if review is None:
        return _failure(
            ValidationFailureCode.MISSING_REVIEW,
            "draft has no semantic-review attestation",
        )
    if review.decision is not ReviewDecision.APPROVED:
        return _failure(ValidationFailureCode.REJECTED_REVIEW, "semantic review was not approved")
    if review.fingerprint_algorithm != SUPPORTED_REVIEW_FINGERPRINT_ALGORITHM:
        return _failure(
            ValidationFailureCode.UNSUPPORTED_METADATA,
            "unsupported review fingerprint algorithm",
        )
    if review.draft_fingerprint != reviewable_fingerprint(draft):
        return _failure(
            ValidationFailureCode.REVIEW_FINGERPRINT_MISMATCH,
            "review does not bind this draft",
        )
    if not draft.completeness.declared_complete or not draft.completeness.basis.strip():
        return _failure(
            ValidationFailureCode.INCOMPLETE_STATE_SPACE,
            "state-space completeness is not attested",
        )
    if (
        draft.proposed_relationship.relationship_type is RelationshipType.CONDITIONAL
        or draft.proposed_relationship.condition is not None
    ):
        return _failure(
            ValidationFailureCode.UNSUPPORTED_CONDITIONAL,
            "conditional relationships are deferred",
        )
    if any(
        binding.classification is not ClaimClassification.BINARY_UNIT for binding in draft.bindings
    ):
        return _failure(
            ValidationFailureCode.UNSUPPORTED_SCALAR,
            "only binary unit-payout claims are supported",
        )
    if draft.schema_version != SUPPORTED_DRAFT_SCHEMA_VERSION:
        return _failure(
            ValidationFailureCode.UNSUPPORTED_METADATA,
            "unsupported draft schema version",
        )
    if draft.validation_method != SUPPORTED_VALIDATION_METHOD:
        return _failure(ValidationFailureCode.UNSUPPORTED_METADATA, "unsupported validation method")
    if not _arity(draft.proposed_relationship):
        return _failure(
            ValidationFailureCode.INVALID_ARITY,
            "relationship arity or membership is invalid",
        )

    proposition_ids = tuple(item.proposition_id for item in draft.propositions)
    proposition_set = set(proposition_ids)
    if not _unique(proposition_ids) or set(proposition_ids) != set(
        draft.proposed_relationship.proposition_ids
    ):
        return _failure(
            ValidationFailureCode.INVALID_ARITY,
            "declaration and proposition membership differ",
        )
    binding_ids = tuple(item.binding_id for item in draft.bindings)
    if not _unique(binding_ids) or not draft.bindings:
        return _failure(ValidationFailureCode.INVALID_ARITY, "binding membership is invalid")
    if any(binding.proposition_id not in proposition_ids for binding in draft.bindings):
        return _failure(
            ValidationFailureCode.INVALID_ARITY,
            "binding references an unknown proposition",
        )
    if set(binding.proposition_id for binding in draft.bindings) != proposition_set:
        return _failure(
            ValidationFailureCode.INVALID_ARITY,
            "every participating proposition requires a venue-native binding",
        )
    if not _critical_provenance_is_present(draft):
        return _failure(
            ValidationFailureCode.MISSING_PROVENANCE,
            "critical claims, states, and completeness require provenance",
        )
    if not _evidence_references_are_closed(draft):
        return _failure(
            ValidationFailureCode.INVALID_EVIDENCE_REFERENCES,
            "evidence references must be unique and closed over draft evidence",
        )
    state_ids = tuple(state.state_id for state in draft.feasible_states)
    if not draft.feasible_states or not _unique(state_ids):
        return _failure(
            ValidationFailureCode.INCOMPLETE_STATE_SPACE,
            "state IDs are missing or duplicated",
        )
    binding_set = set(binding_ids)
    for state in draft.feasible_states:
        if set(state.truth_assignments) != proposition_set:
            return _failure(
                ValidationFailureCode.INCOMPLETE_TRUTH,
                "each feasible state must assign every proposition exactly once",
                state.state_id,
            )
        if set(state.payout_assignments) != binding_set:
            return _failure(
                ValidationFailureCode.INCOMPLETE_PAYOUT,
                "each feasible state must assign every claim payout exactly once",
                state.state_id,
            )
    for state in draft.feasible_states:
        for binding in draft.bindings:
            payout = state.payout_assignments[binding.binding_id]
            if payout not in {ZERO, ONE}:
                return _failure(
                    ValidationFailureCode.INVALID_PAYOUT,
                    "Milestone 2.1 supports only exact zero/one payouts",
                    state.state_id,
                )
            expected = ONE if state.truth_assignments[binding.proposition_id] else ZERO
            if payout != expected:
                return _failure(
                    ValidationFailureCode.INVALID_PAYOUT,
                    "claim payout does not match its bound proposition truth",
                    state.state_id,
                )
    if not _raw_provenance_is_closed(draft):
        return _failure(
            ValidationFailureCode.MISSING_PROVENANCE,
            "required ordered evidence provenance is missing",
        )
    for state in draft.feasible_states:
        if not _relationship_holds(draft, state):
            return _failure(
                ValidationFailureCode.COUNTEREXAMPLE,
                "a supplied feasible state is a relationship counterexample",
                state.state_id,
            )
    assert draft.semantic_review is not None
    review = draft.semantic_review
    assert review is not None
    fingerprint = reviewable_fingerprint(draft)
    certificate_digest = hashlib.sha256(
        stable_json_bytes(
            {
                "certificate_schema_version": RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION,
                "reviewable_content": reviewable_content(draft),
                "semantic_review": review,
                "validation_method": draft.validation_method,
            }
        )
    ).hexdigest()
    certificate = object.__new__(RelationshipCertificate)
    values = {
        "certificate_id": CertificateId(f"cert:{certificate_digest}"),
        "originating_candidate_id": draft.originating_candidate_id,
        "source_draft_id": draft.draft_id,
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
        "feasible_states": draft.feasible_states,
        "completeness": draft.completeness,
        "semantic_review": review,
        "validation_method": draft.validation_method,
        "validation_fingerprint": fingerprint,
        "schema_version": RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION,
    }
    for name, item in values.items():
        object.__setattr__(certificate, name, item)
    return ValidationResult(certificate)


validate_relationship_draft = validate_draft
validate_relationship = validate_draft

__all__ = [
    "ValidationFailure",
    "ValidationFailureCode",
    "ValidationResult",
    "validate_draft",
    "validate_relationship",
    "validate_relationship_draft",
]
