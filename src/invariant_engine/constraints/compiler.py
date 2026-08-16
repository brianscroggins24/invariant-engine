"""Certificate-only deterministic constraint compilation and verification."""

import hashlib
from collections.abc import Mapping
from decimal import Decimal

from invariant_engine.constraints.models import (
    _CONSTRAINT_TRUST_TOKEN,
    CONSTRAINT_SCHEMA_VERSION,
    ClaimBindingIdentity,
    CompilationFailure,
    CompilationFailureCode,
    CompilationResult,
    CompiledPricingConstraint,
    ConstraintId,
    ConstraintRelation,
    LinearTerm,
    TrustedCompiledPricingConstraint,
    VerificationFailure,
    VerificationFailureCode,
    VerificationResult,
)
from invariant_engine.domain.decimal_policy import ONE, ZERO, parse_decimal
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.relationships.candidates import RelationshipCandidate, RelationshipType
from invariant_engine.relationships.certificates import (
    RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION,
    RelationshipCertificate,
)
from invariant_engine.relationships.claims import (
    ClaimBinding,
    ClaimClassification,
    KalshiClaimBinding,
    PolymarketClaimBinding,
    PolymarketOutcomeSide,
)
from invariant_engine.relationships.evidence import (
    CompletenessDeclaration,
    Evidence,
    ReviewDecision,
    SemanticReview,
)
from invariant_engine.relationships.ids import ClaimBindingId, PropositionId
from invariant_engine.relationships.states import FeasibleState
from invariant_engine.relationships.validation import (
    SUPPORTED_DRAFT_SCHEMA_VERSION,
    SUPPORTED_REVIEW_FINGERPRINT_ALGORITHM,
    SUPPORTED_VALIDATION_METHOD,
)
from invariant_engine.serialization import stable_json_bytes

_SUPPORTED_RELATIONSHIPS = frozenset(
    {
        RelationshipType.COMPLEMENT,
        RelationshipType.IMPLICATION,
        RelationshipType.EQUIVALENCE,
        RelationshipType.SUBSET,
        RelationshipType.SUPERSET,
        RelationshipType.MUTUALLY_EXCLUSIVE_SET,
        RelationshipType.EXHAUSTIVE_SET,
        RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
    }
)


def _failure(
    code: CompilationFailureCode, message: str, state_id: str | None = None
) -> CompilationResult:
    return CompilationResult(None, (CompilationFailure(code, message, state_id),))


def _verification_failure(
    code: VerificationFailureCode, message: str, state_id: str | None = None
) -> VerificationResult:
    return VerificationResult(False, (VerificationFailure(code, message, state_id),))


def _satisfies(value: Decimal, relation: ConstraintRelation, bound: Decimal) -> bool:
    if relation is ConstraintRelation.LESS_THAN_OR_EQUAL:
        return value <= bound
    if relation is ConstraintRelation.GREATER_THAN_OR_EQUAL:
        return value >= bound
    return value == bound


def _binding_identity(binding: ClaimBinding) -> ClaimBindingIdentity:
    if isinstance(binding, PolymarketClaimBinding):
        return ClaimBindingIdentity(
            proposition_id=binding.proposition_id,
            claim_binding_id=binding.binding_id,
            classification=binding.classification,
            venue=Venue.POLYMARKET,
            market=binding.market,
            contract=binding.outcome_token,
            native_outcome_side=(
                binding.native_outcome_side.value
                if isinstance(binding.native_outcome_side, PolymarketOutcomeSide)
                else binding.native_outcome_side
            ),
        )
    if isinstance(binding, KalshiClaimBinding):
        return ClaimBindingIdentity(
            proposition_id=binding.proposition_id,
            claim_binding_id=binding.binding_id,
            classification=binding.classification,
            venue=Venue.KALSHI,
            market=binding.market,
            native_side=binding.native_side.value,
        )
    raise DomainError("unsupported claim binding type")


def _terms_and_relation(
    relationship: RelationshipType,
    proposition_ids: tuple[PropositionId, ...],
    binding_ids: Mapping[PropositionId, ClaimBindingId],
) -> tuple[tuple[LinearTerm, ...], ConstraintRelation, Decimal]:
    def term(index: int, coefficient: str) -> LinearTerm:
        proposition_id = proposition_ids[index]
        return LinearTerm(proposition_id, binding_ids[proposition_id], Decimal(coefficient))

    if relationship is RelationshipType.COMPLEMENT:
        return (term(0, "1"), term(1, "1")), ConstraintRelation.EQUAL, ONE
    if relationship in {RelationshipType.IMPLICATION, RelationshipType.SUBSET}:
        return (term(0, "1"), term(1, "-1")), ConstraintRelation.LESS_THAN_OR_EQUAL, ZERO
    if relationship is RelationshipType.EQUIVALENCE:
        return (term(0, "1"), term(1, "-1")), ConstraintRelation.EQUAL, ZERO
    if relationship is RelationshipType.SUPERSET:
        return (term(0, "1"), term(1, "-1")), ConstraintRelation.GREATER_THAN_OR_EQUAL, ZERO
    if relationship is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        return (
            tuple(term(index, "1") for index in range(len(proposition_ids))),
            ConstraintRelation.LESS_THAN_OR_EQUAL,
            ONE,
        )
    if relationship is RelationshipType.EXHAUSTIVE_SET:
        return (
            tuple(term(index, "1") for index in range(len(proposition_ids))),
            ConstraintRelation.GREATER_THAN_OR_EQUAL,
            ONE,
        )
    if relationship is RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION:
        return (
            tuple(term(index, "1") for index in range(len(proposition_ids))),
            ConstraintRelation.EQUAL,
            ONE,
        )
    raise DomainError("relationship is not supported by constraint-v1")


def _certificate_reviewable_content(certificate: RelationshipCertificate) -> dict[str, object]:
    """Rebuild the validator's exact draft review content from certificate fields."""

    return {
        "draft_id": certificate.source_draft_id,
        "originating_candidate_id": certificate.originating_candidate_id,
        "schema_version": SUPPORTED_DRAFT_SCHEMA_VERSION,
        "propositions": certificate.propositions,
        "bindings": certificate.bindings,
        "proposed_relationship": certificate.proposed_relationship,
        "evidence": certificate.evidence,
        "event_scope": certificate.event_scope,
        "thresholds": certificate.thresholds,
        "observation_period": certificate.observation_period,
        "close_time": certificate.close_time,
        "resolution_time": certificate.resolution_time,
        "resolution_sources": certificate.resolution_sources,
        "cancellation_behavior": certificate.cancellation_behavior,
        "void_behavior": certificate.void_behavior,
        "refund_behavior": certificate.refund_behavior,
        "payout_structure": certificate.payout_structure,
        "edge_cases": certificate.edge_cases,
        "assumptions": certificate.assumptions,
        "uncertainties": certificate.uncertainties,
        "evidence_provenance": certificate.evidence_provenance,
        "validation_method": certificate.validation_method,
        "feasible_states": certificate.feasible_states,
        "completeness": certificate.completeness,
    }


def _certificate_integrity_failure(
    certificate: RelationshipCertificate,
) -> CompilationFailure | None:
    if certificate.schema_version != RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION:
        return CompilationFailure(
            CompilationFailureCode.UNSUPPORTED_SCHEMA,
            "certificate schema version is not supported by constraint-v1",
        )
    if certificate.validation_method != SUPPORTED_VALIDATION_METHOD:
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate validation method is not supported",
        )
    review = certificate.semantic_review
    if not isinstance(review, SemanticReview):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate semantic review is missing or malformed",
        )
    if review.fingerprint_algorithm != SUPPORTED_REVIEW_FINGERPRINT_ALGORITHM:
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate semantic review fingerprint algorithm is unsupported",
        )
    if review.decision is not ReviewDecision.APPROVED:
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate semantic review is not approved",
        )
    reviewable_content = _certificate_reviewable_content(certificate)
    reviewable_fingerprint = hashlib.sha256(stable_json_bytes(reviewable_content)).hexdigest()
    if review.draft_fingerprint != reviewable_fingerprint:
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "semantic review fingerprint does not close over certificate content",
        )
    if certificate.validation_fingerprint != reviewable_fingerprint:
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate validation fingerprint does not match reviewed content",
        )
    certificate_digest = hashlib.sha256(
        stable_json_bytes(
            {
                "certificate_schema_version": RELATIONSHIP_CERTIFICATE_SCHEMA_VERSION,
                "reviewable_content": reviewable_content,
                "semantic_review": review,
                "validation_method": certificate.validation_method,
            }
        )
    ).hexdigest()
    if certificate.certificate_id.value != f"cert:{certificate_digest}":
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate ID does not match the accepted validator digest",
        )
    completeness = certificate.completeness
    if not isinstance(completeness, CompletenessDeclaration):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate completeness declaration is malformed",
        )
    if not completeness.declared_complete or not completeness.basis.strip():
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate completeness is not declared and structurally valid",
        )
    if not completeness.attestation_scope.strip():
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate completeness attestation scope is empty",
        )
    return None


def _certificate_evidence_and_provenance_failure(
    certificate: RelationshipCertificate,
) -> CompilationFailure | None:
    evidence = certificate.evidence
    if (
        not isinstance(evidence, tuple)
        or not evidence
        or any(not isinstance(item, Evidence) for item in evidence)
    ):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate evidence records are missing or malformed",
        )
    evidence_ids = tuple(item.evidence_id for item in evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate evidence IDs are not unique",
        )
    evidence_set = set(evidence_ids)
    groups = [
        certificate.resolution_sources,
        certificate.completeness.evidence_ids,
    ]
    for binding in certificate.bindings:
        groups.append(binding.evidence_ids)
    for state in certificate.feasible_states:
        groups.append(state.evidence_ids)
    if any(
        len(group) != len(set(group)) or any(item not in evidence_set for item in group)
        for group in groups
    ):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate evidence references are not closed and unique",
        )
    provenance = certificate.evidence_provenance
    if (
        not isinstance(provenance, tuple)
        or not provenance
        or len(set(provenance)) != len(provenance)
    ):
        return CompilationFailure(
            CompilationFailureCode.MISSING_PROVENANCE,
            "certificate requires ordered unique evidence provenance",
        )
    if any(not isinstance(item, RawReference) for item in provenance):
        return CompilationFailure(
            CompilationFailureCode.MISSING_PROVENANCE,
            "certificate evidence provenance contains an invalid reference",
        )
    nested = list(certificate.completeness.raw_refs) + list(provenance)
    for item in evidence:
        nested.extend(item.raw_refs)
        if not item.locator and not item.raw_refs:
            return CompilationFailure(
                CompilationFailureCode.MISSING_PROVENANCE,
                "certificate evidence requires a locator or raw provenance",
            )
    for binding in certificate.bindings:
        nested.extend(binding.raw_refs)
        if not binding.evidence_ids and not binding.raw_refs:
            return CompilationFailure(
                CompilationFailureCode.MISSING_PROVENANCE,
                "certificate bindings require direct evidence or raw provenance",
            )
    for state in certificate.feasible_states:
        nested.extend(state.raw_refs)
        if not state.evidence_ids and not state.raw_refs:
            return CompilationFailure(
                CompilationFailureCode.MISSING_PROVENANCE,
                "certificate states require direct evidence or raw provenance",
            )
    if any(reference not in provenance for reference in nested):
        return CompilationFailure(
            CompilationFailureCode.MISSING_PROVENANCE,
            "certificate nested raw provenance is not closed over the ordered lineage",
        )
    return None


def _certificate_shape(certificate: RelationshipCertificate) -> CompilationFailure | None:
    integrity_failure = _certificate_integrity_failure(certificate)
    if integrity_failure is not None:
        return integrity_failure
    evidence_failure = _certificate_evidence_and_provenance_failure(certificate)
    if evidence_failure is not None:
        return evidence_failure
    if not isinstance(certificate.certificate_id.value, str):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE, "certificate ID is invalid"
        )
    provenance = certificate.evidence_provenance
    if (
        not isinstance(provenance, tuple)
        or not provenance
        or any(not isinstance(item, RawReference) for item in provenance)
        or len(set(provenance)) != len(provenance)
    ):
        return CompilationFailure(
            CompilationFailureCode.MISSING_PROVENANCE,
            "certificate requires ordered unique evidence provenance",
        )
    if not certificate.validation_fingerprint:
        return CompilationFailure(
            CompilationFailureCode.MISSING_PROVENANCE,
            "certificate validation fingerprint is required",
        )
    propositions = certificate.propositions
    declaration = certificate.proposed_relationship
    proposition_ids = tuple(item.proposition_id for item in propositions)
    if len(set(proposition_ids)) != len(proposition_ids):
        return CompilationFailure(
            CompilationFailureCode.DUPLICATE_PROPOSITION,
            "certificate propositions contain duplicate IDs",
        )
    declaration_ids = tuple(declaration.proposition_ids)
    if len(set(declaration_ids)) != len(declaration_ids) or set(declaration_ids) != set(
        proposition_ids
    ):
        return CompilationFailure(
            CompilationFailureCode.DECLARATION_MISMATCH,
            "declaration and certificate proposition membership must match uniquely",
        )
    if (
        declaration.relationship_type is RelationshipType.CONDITIONAL
        or declaration.condition is not None
    ):
        return CompilationFailure(
            CompilationFailureCode.UNSUPPORTED_CONDITIONAL,
            "conditional relationships are not representable in constraint-v1",
        )
    if declaration.relationship_type not in _SUPPORTED_RELATIONSHIPS:
        return CompilationFailure(
            CompilationFailureCode.UNSUPPORTED_RELATIONSHIP,
            "relationship type is not supported by constraint-v1",
        )
    bindings = certificate.bindings
    binding_ids = tuple(item.binding_id for item in bindings)
    if len(set(binding_ids)) != len(binding_ids):
        return CompilationFailure(
            CompilationFailureCode.DUPLICATE_BINDING,
            "certificate bindings contain duplicate IDs",
        )
    if any(binding.classification is not ClaimClassification.BINARY_UNIT for binding in bindings):
        return CompilationFailure(
            CompilationFailureCode.UNSUPPORTED_SCALAR,
            "constraint-v1 accepts only binary unit-payout bindings",
        )
    proposition_set = set(declaration_ids)
    if any(binding.proposition_id not in proposition_set for binding in bindings):
        return CompilationFailure(
            CompilationFailureCode.UNKNOWN_BINDING_PROPOSITION,
            "binding references a proposition outside the declaration",
        )
    if len({binding.proposition_id for binding in bindings}) != len(bindings):
        return CompilationFailure(
            CompilationFailureCode.DUPLICATE_BINDING_PROPOSITION,
            "constraint-v1 requires exactly one binding per proposition",
        )
    binding_props = {binding.proposition_id for binding in bindings}
    if binding_props != proposition_set:
        return CompilationFailure(
            CompilationFailureCode.MISSING_BINDING,
            "each declared proposition requires one claim binding",
        )
    for binding in bindings:
        if not binding.raw_refs or any(
            reference not in provenance for reference in binding.raw_refs
        ):
            return CompilationFailure(
                CompilationFailureCode.MISSING_PROVENANCE,
                "each binding must retain closed certificate provenance",
            )
    if not certificate.feasible_states:
        return CompilationFailure(
            CompilationFailureCode.NO_FEASIBLE_STATES,
            "certificate must contain at least one feasible state",
        )
    state_ids = tuple(state.state_id for state in certificate.feasible_states)
    if any(not isinstance(state, FeasibleState) for state in certificate.feasible_states) or len(
        set(state_ids)
    ) != len(state_ids):
        return CompilationFailure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate feasible states must be unique FeasibleState records",
        )
    binding_set = set(binding_ids)
    for state in certificate.feasible_states:
        if set(state.truth_assignments) != proposition_set:
            return CompilationFailure(
                CompilationFailureCode.INVALID_CERTIFICATE,
                "certificate feasible states must assign every declared proposition",
                state.state_id.value,
            )
        if set(state.payout_assignments) != binding_set:
            return CompilationFailure(
                CompilationFailureCode.INVALID_CERTIFICATE,
                "certificate feasible states must contain the complete certified payout map",
                state.state_id.value,
            )
    return None


def _constraint_identity_content(constraint: CompiledPricingConstraint) -> dict[str, object]:
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


def constraint_identity_matches(constraint: CompiledPricingConstraint) -> bool:
    try:
        expected = (
            "constraint:"
            + hashlib.sha256(
                stable_json_bytes(_constraint_identity_content(constraint))
            ).hexdigest()
        )
        return constraint.constraint_id.value == expected
    except (AttributeError, DomainError, TypeError, ValueError):
        return False


def _expected_constraint_parts(
    certificate: RelationshipCertificate,
) -> tuple[tuple[LinearTerm, ...], ConstraintRelation, Decimal, tuple[ClaimBindingIdentity, ...]]:
    proposition_ids = tuple(certificate.proposed_relationship.proposition_ids)
    binding_by_proposition = {binding.proposition_id: binding for binding in certificate.bindings}
    terms, relation, bound = _terms_and_relation(
        certificate.proposed_relationship.relationship_type,
        proposition_ids,
        {key: item.binding_id for key, item in binding_by_proposition.items()},
    )
    identities = tuple(
        _binding_identity(binding_by_proposition[term.proposition_id]) for term in terms
    )
    return terms, relation, bound, identities


def _verify_constraint(
    constraint: CompiledPricingConstraint, certificate: RelationshipCertificate
) -> VerificationResult:
    """Verify a proposed linear constraint against every certified payoff state."""

    if not isinstance(constraint, CompiledPricingConstraint) or not isinstance(
        certificate, RelationshipCertificate
    ):
        return _verification_failure(
            VerificationFailureCode.WRONG_TYPE,
            "verification requires a compiled constraint and RelationshipCertificate",
        )
    shape_failure = _certificate_shape(certificate)
    if shape_failure is not None:
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            shape_failure.message,
        )
    try:
        expected_terms, expected_relation, expected_bound, expected_identities = (
            _expected_constraint_parts(certificate)
        )
        if constraint.certificate_id != certificate.certificate_id:
            raise DomainError("constraint certificate ID does not match certificate")
        if constraint.certificate_schema_version != certificate.schema_version:
            raise DomainError("constraint certificate schema does not match certificate")
        if constraint.certificate_validation_fingerprint != certificate.validation_fingerprint:
            raise DomainError("constraint validation fingerprint does not match certificate")
        if constraint.relationship_type is not certificate.proposed_relationship.relationship_type:
            raise DomainError("constraint relationship type does not match certificate")
        if constraint.certificate_provenance != certificate.evidence_provenance:
            raise DomainError("constraint provenance does not match certificate")
        if constraint.terms != expected_terms:
            raise DomainError("constraint terms do not match declaration semantics")
        if constraint.relation is not expected_relation or constraint.bound != expected_bound:
            raise DomainError("constraint relation or bound does not match declaration semantics")
        if constraint.binding_identities != expected_identities:
            raise DomainError("constraint binding identities do not match certificate bindings")
        if not constraint_identity_matches(constraint):
            raise DomainError("constraint ID does not match its complete material content")
    except (AttributeError, DomainError, TypeError, ValueError) as exc:
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            f"constraint does not close over the supplied certificate: {exc}",
        )
    if constraint.schema_version != CONSTRAINT_SCHEMA_VERSION:
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            "unsupported constraint schema version",
        )
    try:
        verified_bound = parse_decimal(constraint.bound, field="constraint bound")
        if not isinstance(constraint.relation, ConstraintRelation):
            raise DomainError("constraint relation is unsupported")
        for term in constraint.terms:
            if not isinstance(term, LinearTerm):
                raise DomainError("constraint contains a non-linear term")
            parse_decimal(term.coefficient, field="term coefficient")
    except (DomainError, TypeError, ValueError) as exc:
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            f"constraint contains an invalid Decimal or relation: {exc}",
        )
    if not certificate.feasible_states:
        return _verification_failure(
            VerificationFailureCode.NO_FEASIBLE_STATES,
            "certificate has no feasible payoff states",
        )
    certificate_bindings = {binding.binding_id: binding for binding in certificate.bindings}
    if len(certificate_bindings) != len(certificate.bindings):
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            "certificate binding IDs are not unique",
        )
    term_bindings = tuple(term.claim_binding_id for term in constraint.terms)
    expected_binding_ids = tuple(binding.binding_id for binding in certificate.bindings)
    if (
        len(set(term_bindings)) != len(term_bindings)
        or set(term_bindings) != set(expected_binding_ids)
        or len(term_bindings) != len(expected_binding_ids)
    ):
        return _verification_failure(
            VerificationFailureCode.UNKNOWN_BINDING,
            "constraint terms must map one-to-one to every certificate binding",
        )
    if any(
        term.proposition_id != certificate_bindings[term.claim_binding_id].proposition_id
        for term in constraint.terms
    ):
        return _verification_failure(
            VerificationFailureCode.UNKNOWN_BINDING,
            "constraint term proposition does not match its binding",
        )
    expected_bindings = set(certificate_bindings)
    for state in certificate.feasible_states:
        state_id = state.state_id.value
        assignments = state.payout_assignments
        if set(assignments) - expected_bindings:
            return _verification_failure(
                VerificationFailureCode.UNEXPECTED_PAYOUT,
                "feasible state contains an unexpected payout assignment",
                state_id,
            )
        if expected_bindings - set(assignments):
            return _verification_failure(
                VerificationFailureCode.MISSING_PAYOUT,
                "feasible state is missing a required payout assignment",
                state_id,
            )
        expression = ZERO
        for term in constraint.terms:
            try:
                payout = parse_decimal(
                    assignments[term.claim_binding_id],
                    field=f"payout[{term.claim_binding_id.value}]",
                )
            except DomainError:
                return _verification_failure(
                    VerificationFailureCode.UNSUPPORTED_PAYOUT,
                    "feasible state payout is not a finite Decimal",
                    state_id,
                )
            if payout not in {ZERO, ONE}:
                return _verification_failure(
                    VerificationFailureCode.UNSUPPORTED_PAYOUT,
                    "constraint-v1 supports only zero/one payouts",
                    state_id,
                )
            expression += parse_decimal(term.coefficient, field="term coefficient") * payout
        if not _satisfies(expression, constraint.relation, verified_bound):
            return _verification_failure(
                VerificationFailureCode.VIOLATION,
                "feasible payoff state violates the proposed constraint",
                state_id,
            )
    return VerificationResult(True)


def verify_constraint(
    constraint: CompiledPricingConstraint, certificate: RelationshipCertificate
) -> VerificationResult:
    """Verify a proposed constraint and convert malformed input to a failure."""

    try:
        return _verify_constraint(constraint, certificate)
    except Exception:
        return _verification_failure(
            VerificationFailureCode.INVALID_CONSTRAINT,
            "constraint verification failed closed",
        )


def compile_certificate(value: object) -> CompilationResult:
    """Compile only a validator-produced certificate; all failures are structured."""

    if isinstance(value, (RelationshipCandidate,)):
        return _failure(
            CompilationFailureCode.WRONG_TYPE,
            "RelationshipCandidate objects cannot be compiled",
        )
    if not isinstance(value, RelationshipCertificate):
        return _failure(
            CompilationFailureCode.WRONG_TYPE,
            "compiler requires a validator-produced RelationshipCertificate",
        )
    certificate = value
    try:
        shape_failure = _certificate_shape(certificate)
        if shape_failure is not None:
            return CompilationResult(None, (shape_failure,))
        proposition_ids = tuple(certificate.proposed_relationship.proposition_ids)
        binding_by_proposition = {
            binding.proposition_id: binding for binding in certificate.bindings
        }
        terms, relation, bound = _terms_and_relation(
            certificate.proposed_relationship.relationship_type,
            proposition_ids,
            {key: item.binding_id for key, item in binding_by_proposition.items()},
        )
        identities = tuple(
            _binding_identity(binding_by_proposition[term.proposition_id]) for term in terms
        )
        canonical = {
            "schema_version": CONSTRAINT_SCHEMA_VERSION,
            "certificate_id": certificate.certificate_id,
            "certificate_schema_version": certificate.schema_version,
            "certificate_validation_fingerprint": certificate.validation_fingerprint,
            "relationship_type": certificate.proposed_relationship.relationship_type,
            "terms": terms,
            "relation": relation,
            "bound": bound,
            "certificate_provenance": certificate.evidence_provenance,
            "binding_identities": identities,
        }
        constraint_id = ConstraintId(
            "constraint:" + hashlib.sha256(stable_json_bytes(canonical)).hexdigest()
        )
        constraint = CompiledPricingConstraint(
            schema_version=CONSTRAINT_SCHEMA_VERSION,
            constraint_id=constraint_id,
            certificate_id=certificate.certificate_id,
            certificate_schema_version=certificate.schema_version,
            certificate_validation_fingerprint=certificate.validation_fingerprint,
            relationship_type=certificate.proposed_relationship.relationship_type,
            terms=terms,
            relation=relation,
            bound=bound,
            certificate_provenance=certificate.evidence_provenance,
            binding_identities=identities,
        )
        verification = verify_constraint(constraint, certificate)
        if not verification.ok:
            failure = verification.failures[0]
            return _failure(
                CompilationFailureCode.PAYOFF_VERIFICATION,
                failure.message,
                failure.state_id,
            )
        return CompilationResult(
            TrustedCompiledPricingConstraint._from_verified(
                constraint, token=_CONSTRAINT_TRUST_TOKEN
            )
        )
    except Exception:
        return _failure(
            CompilationFailureCode.INVALID_CERTIFICATE,
            "certificate cannot be represented deterministically",
        )


compile_constraint = compile_certificate
verify_payoff_constraint = verify_constraint

__all__ = [
    "compile_certificate",
    "compile_constraint",
    "verify_constraint",
    "verify_payoff_constraint",
    "constraint_identity_matches",
]
