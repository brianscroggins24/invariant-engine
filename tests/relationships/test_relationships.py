import json
import socket
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.relationships import (
    CandidateId,
    ClaimBindingId,
    ClaimClassification,
    CompletenessDeclaration,
    DraftId,
    Evidence,
    EvidenceId,
    EvidenceKind,
    FeasibleState,
    FeasibleStateId,
    KalshiClaimBinding,
    PolymarketClaimBinding,
    Proposition,
    PropositionId,
    RelationshipCandidate,
    RelationshipCertificate,
    RelationshipCertificateDraft,
    RelationshipDeclaration,
    RelationshipType,
    ReviewDecision,
    SemanticReview,
    SemanticReviewId,
    TerminalStateKind,
    Threshold,
    ValidationFailureCode,
    validate_draft,
)
from invariant_engine.relationships.certificates import reviewable_fingerprint
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import KalshiMarketIdentity, KalshiNativeSideKind

UTC_TIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
POLY_RAW = RawReference("poly-raw", Venue.POLYMARKET)
KALSHI_RAW = RawReference("kalshi-raw", Venue.KALSHI)
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "relationships" / "relationships.json"
)
FIXTURE_METADATA = json.loads(FIXTURE_PATH.read_text())


def _evidence(*, raw_refs: tuple[RawReference, ...] = (POLY_RAW,)) -> Evidence:
    return Evidence(
        evidence_id=EvidenceId("e-rule"),
        kind=EvidenceKind.MARKET_RULE,
        rule_text="Synthetic rule text supplied for deterministic testing.",
        locator="fixtures/relationships/relationships.json#rule",
        raw_refs=raw_refs,
        synthetic=True,
    )


def _bindings(
    propositions: tuple[Proposition, ...], *, cross_venue: bool = False, kalshi_only: bool = False
):
    result = []
    for index, proposition in enumerate(propositions):
        if kalshi_only or (cross_venue and index == 1):
            kalshi_example = FIXTURE_METADATA["examples"]["kalshi"]
            result.append(
                KalshiClaimBinding(
                    proposition_id=proposition.proposition_id,
                    binding_id=ClaimBindingId(f"b-{index}"),
                    classification=ClaimClassification.BINARY_UNIT,
                    market=KalshiMarketIdentity(
                        kalshi_example["market_ticker"], kalshi_example["market_id"]
                    ),
                    native_side=KalshiNativeSideKind.NO,
                    evidence_ids=(EvidenceId("e-rule"),),
                    raw_refs=(KALSHI_RAW,),
                )
            )
        else:
            polymarket_example = FIXTURE_METADATA["examples"]["polymarket"]
            result.append(
                PolymarketClaimBinding(
                    proposition_id=proposition.proposition_id,
                    binding_id=ClaimBindingId(f"b-{index}"),
                    classification=ClaimClassification.BINARY_UNIT,
                    market=MarketReference(polymarket_example["market"], Venue.POLYMARKET),
                    outcome_token=ContractReference(
                        polymarket_example["outcome_token"], Venue.POLYMARKET
                    ),
                    evidence_ids=(EvidenceId("e-rule"),),
                    raw_refs=(POLY_RAW,),
                )
            )
    return tuple(result)


def _truth_vectors(relationship: RelationshipType, count: int) -> tuple[tuple[bool, ...], ...]:
    if count == 2 and relationship in {RelationshipType.IMPLICATION, RelationshipType.SUBSET}:
        return ((False, False), (False, True), (True, True))
    if count == 2 and relationship is RelationshipType.SUPERSET:
        return ((False, False), (True, False), (True, True))
    if count == 2 and relationship is RelationshipType.EQUIVALENCE:
        return ((False, False), (True, True))
    if count == 2 and relationship is RelationshipType.COMPLEMENT:
        return ((True, False), (False, True))
    if relationship is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        return ((False,) * count,) + tuple(
            tuple(index == member for index in range(count)) for member in range(count)
        )
    if relationship is RelationshipType.EXHAUSTIVE_SET:
        return tuple(tuple(index == member for index in range(count)) for member in range(count))
    if relationship is RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION:
        return tuple(tuple(index == member for index in range(count)) for member in range(count))
    raise AssertionError(relationship)


def _draft(
    relationship: RelationshipType,
    *,
    count: int = 2,
    cross_venue: bool = False,
    kalshi_only: bool = False,
    terminal_kinds: tuple[TerminalStateKind, ...] = (TerminalStateKind.NORMAL,),
) -> RelationshipCertificateDraft:
    propositions = tuple(
        Proposition(PropositionId(f"p-{index}"), f"Synthetic proposition {index}")
        for index in range(count)
    )
    declaration = RelationshipDeclaration(
        relationship,
        tuple(item.proposition_id for item in propositions),
    )
    bindings = _bindings(propositions, cross_venue=cross_venue, kalshi_only=kalshi_only)
    fixture_raw_refs = (
        (KALSHI_RAW,) if kalshi_only else (POLY_RAW, KALSHI_RAW) if cross_venue else (POLY_RAW,)
    )
    evidence = (_evidence(raw_refs=fixture_raw_refs),)
    state_list = []
    vectors = _truth_vectors(relationship, count)
    for state_index, vector in enumerate(vectors):
        truth = {propositions[index].proposition_id: value for index, value in enumerate(vector)}
        payouts = {
            binding.binding_id: Decimal("1") if truth[binding.proposition_id] else Decimal("0")
            for binding in bindings
        }
        state_list.append(
            FeasibleState(
                state_id=FeasibleStateId(f"s-{state_index}"),
                terminal_kind=terminal_kinds[state_index % len(terminal_kinds)],
                truth_assignments=truth,
                payout_assignments=payouts,
                evidence_ids=(EvidenceId("e-rule"),),
                raw_refs=fixture_raw_refs,
            )
        )
    candidate = RelationshipCandidate(
        CandidateId("candidate-1"),
        tuple(item.proposition_id for item in propositions),
        declaration,
        evidence_ids=(EvidenceId("e-rule"),),
        raw_refs=fixture_raw_refs,
    )
    draft = RelationshipCertificateDraft(
        draft_id=DraftId(f"draft-{relationship.value}"),
        originating_candidate_id=candidate.candidate_id,
        propositions=propositions,
        bindings=bindings,
        proposed_relationship=declaration,
        evidence=evidence,
        event_scope="synthetic event scope",
        thresholds=(Threshold("threshold", Decimal("10"), "units"),),
        observation_period=None,
        close_time=UTC_TIME,
        resolution_time=UTC_TIME,
        resolution_sources=(EvidenceId("e-rule"),),
        cancellation_behavior="explicitly modeled if supplied",
        void_behavior="explicitly modeled if supplied",
        refund_behavior="explicitly modeled if supplied",
        payout_structure="one unit for true, zero for false",
        edge_cases=("synthetic edge case",),
        assumptions=("synthetic assumption",),
        uncertainties=("synthetic uncertainty",),
        evidence_provenance=(KALSHI_RAW, POLY_RAW) if cross_venue else fixture_raw_refs,
        validation_method="truth-payoff-exhaustive-supplied-v1",
        feasible_states=tuple(state_list),
        completeness=CompletenessDeclaration(
            True,
            "Synthetic fixture declares its supplied state list complete for this test model.",
            "synthetic-review-only",
            evidence_ids=(EvidenceId("e-rule"),),
            raw_refs=fixture_raw_refs,
        ),
    )
    review = SemanticReview.for_draft(
        draft,
        review_id=SemanticReviewId("review-1"),
        reviewer="synthetic-reviewer",
        decision=ReviewDecision.APPROVED,
        reviewed_at=UTC_TIME,
        basis="Synthetic fixture review only; not production authority.",
        authority_scope="synthetic-fixture-only",
    )
    return draft.with_semantic_review(review)


def _review_again(
    draft: RelationshipCertificateDraft, review_id: str
) -> RelationshipCertificateDraft:
    return draft.with_semantic_review(
        SemanticReview.for_draft(
            draft,
            review_id=SemanticReviewId(review_id),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Updated synthetic fixture review; not production authority.",
            authority_scope="synthetic-fixture-only",
        )
    )


def _counterexample_draft(
    relationship: RelationshipType, count: int, vector: tuple[bool, ...]
) -> RelationshipCertificateDraft:
    draft = _draft(relationship, count=count)
    propositions = {
        item.proposition_id: value for item, value in zip(draft.propositions, vector, strict=True)
    }
    state = draft.feasible_states[0]
    payouts = {
        binding.binding_id: Decimal("1") if propositions[binding.proposition_id] else Decimal("0")
        for binding in draft.bindings
    }
    changed_state = replace(state, truth_assignments=propositions, payout_assignments=payouts)
    return _review_again(
        replace(draft, feasible_states=(changed_state,) + draft.feasible_states[1:]),
        f"review-counterexample-{relationship.value}",
    )


@pytest.mark.parametrize(
    ("relationship", "count"),
    [
        (RelationshipType.IMPLICATION, 2),
        (RelationshipType.EQUIVALENCE, 2),
        (RelationshipType.COMPLEMENT, 2),
        (RelationshipType.SUBSET, 2),
        (RelationshipType.SUPERSET, 2),
        (RelationshipType.MUTUALLY_EXCLUSIVE_SET, 3),
        (RelationshipType.EXHAUSTIVE_SET, 3),
        (RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION, 3),
    ],
)
def test_all_supported_relationships_validate(relationship: RelationshipType, count: int) -> None:
    result = validate_draft(_draft(relationship, count=count))
    assert result.ok, result.failures
    assert isinstance(result.certificate, RelationshipCertificate)


@pytest.mark.parametrize(
    ("relationship", "count", "counterexample"),
    [
        (RelationshipType.IMPLICATION, 2, (True, False)),
        (RelationshipType.EQUIVALENCE, 2, (True, False)),
        (RelationshipType.COMPLEMENT, 2, (False, False)),
        (RelationshipType.SUBSET, 2, (True, False)),
        (RelationshipType.SUPERSET, 2, (False, True)),
        (RelationshipType.MUTUALLY_EXCLUSIVE_SET, 3, (True, True, False)),
        (RelationshipType.EXHAUSTIVE_SET, 3, (False, False, False)),
        (RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION, 3, (True, True, False)),
    ],
)
def test_all_supported_relationships_reject_counterexamples(
    relationship: RelationshipType, count: int, counterexample: tuple[bool, ...]
) -> None:
    result = validate_draft(_counterexample_draft(relationship, count, counterexample))
    assert result.failure.code is ValidationFailureCode.COUNTEREXAMPLE


@pytest.mark.parametrize(
    "invalid_kind",
    ("rejected", "incomplete", "scalar", "conditional", "counterexample"),
)
def test_no_callable_certificate_factory_exists(invalid_kind: str) -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    if invalid_kind == "rejected":
        draft = replace(
            draft,
            semantic_review=replace(draft.semantic_review, decision=ReviewDecision.REJECTED),
        )
    elif invalid_kind == "incomplete":
        draft = _review_again(
            replace(draft, completeness=replace(draft.completeness, declared_complete=False)),
            "review-direct-incomplete",
        )
    elif invalid_kind == "scalar":
        draft = _review_again(
            replace(
                draft,
                bindings=(replace(draft.bindings[0], classification=ClaimClassification.SCALAR),)
                + draft.bindings[1:],
            ),
            "review-direct-scalar",
        )
    elif invalid_kind == "conditional":
        draft = _review_again(
            replace(
                draft,
                proposed_relationship=RelationshipDeclaration(
                    RelationshipType.IMPLICATION,
                    draft.proposed_relationship.proposition_ids,
                    condition="if C",
                ),
            ),
            "review-direct-conditional",
        )
    else:
        draft = _counterexample_draft(RelationshipType.IMPLICATION, 2, (True, False))
    assert not hasattr(RelationshipCertificate, "_from_validated")
    assert validate_draft(draft).certificate is None
    with pytest.raises(TypeError):
        RelationshipCertificate()  # type: ignore[call-arg]


def test_candidate_is_not_a_draft_and_certificate_has_no_public_constructor() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    candidate = RelationshipCandidate(
        CandidateId("candidate-only"),
        draft.proposed_relationship.proposition_ids,
        draft.proposed_relationship,
    )
    assert validate_draft(candidate).failure is not None
    assert validate_draft(candidate).failure.code is ValidationFailureCode.WRONG_TYPE
    with pytest.raises(TypeError):
        RelationshipCertificate()  # type: ignore[call-arg]


def test_review_is_required_rejected_and_bound_to_exact_draft() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    assert (
        validate_draft(replace(draft, semantic_review=None)).failure.code
        is ValidationFailureCode.MISSING_REVIEW
    )
    rejected = replace(draft.semantic_review, decision=ReviewDecision.REJECTED)
    assert (
        validate_draft(replace(draft, semantic_review=rejected)).failure.code
        is ValidationFailureCode.REJECTED_REVIEW
    )
    changed = replace(draft, event_scope="changed after review")
    assert validate_draft(changed).failure.code is ValidationFailureCode.REVIEW_FINGERPRINT_MISMATCH


def test_review_cannot_be_reused_after_identity_reassignment() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    changed_draft = replace(draft, draft_id=DraftId("reassigned-draft"))
    changed_candidate = replace(draft, originating_candidate_id=CandidateId("reassigned-candidate"))
    assert (
        validate_draft(changed_draft).failure.code
        is ValidationFailureCode.REVIEW_FINGERPRINT_MISMATCH
    )
    assert (
        validate_draft(changed_candidate).failure.code
        is ValidationFailureCode.REVIEW_FINGERPRINT_MISMATCH
    )


def test_conditions_on_supported_relationships_are_unsupported() -> None:
    draft = _draft(RelationshipType.SUBSET)
    declaration = RelationshipDeclaration(
        RelationshipType.SUBSET,
        draft.proposed_relationship.proposition_ids,
        condition="if C",
    )
    conditional = _review_again(
        replace(draft, proposed_relationship=declaration), "review-conditioned-subset"
    )
    assert validate_draft(conditional).failure.code is ValidationFailureCode.UNSUPPORTED_CONDITIONAL


def test_evidence_references_are_closed_and_provenance_is_complete() -> None:
    draft = _draft(RelationshipType.IMPLICATION, cross_venue=True)
    dangling_binding = replace(draft.bindings[1], evidence_ids=(EvidenceId("missing-evidence"),))
    dangling = _review_again(
        replace(draft, bindings=(draft.bindings[0], dangling_binding)),
        "review-dangling-evidence",
    )
    assert (
        validate_draft(dangling).failure.code is ValidationFailureCode.INVALID_EVIDENCE_REFERENCES
    )

    duplicate_records = _review_again(
        replace(draft, evidence=draft.evidence + draft.evidence),
        "review-duplicate-evidence",
    )
    assert (
        validate_draft(duplicate_records).failure.code
        is ValidationFailureCode.INVALID_EVIDENCE_REFERENCES
    )

    incomplete_cross_venue = _review_again(
        replace(draft, evidence_provenance=(POLY_RAW,)),
        "review-incomplete-cross-venue-provenance",
    )
    assert (
        validate_draft(incomplete_cross_venue).failure.code
        is ValidationFailureCode.MISSING_PROVENANCE
    )


@pytest.mark.parametrize("critical_object", ("binding", "state", "completeness"))
def test_critical_objects_require_direct_provenance(critical_object: str) -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    if critical_object == "binding":
        changed_binding = replace(draft.bindings[0], evidence_ids=(), raw_refs=())
        changed = replace(draft, bindings=(changed_binding,) + draft.bindings[1:])
    elif critical_object == "state":
        changed_state = replace(draft.feasible_states[0], evidence_ids=(), raw_refs=())
        changed = replace(draft, feasible_states=(changed_state,) + draft.feasible_states[1:])
    else:
        changed = replace(
            draft,
            completeness=replace(draft.completeness, evidence_ids=(), raw_refs=()),
        )
    changed = _review_again(changed, f"review-empty-{critical_object}-provenance")
    assert validate_draft(changed).failure.code is ValidationFailureCode.MISSING_PROVENANCE


def test_every_participating_proposition_requires_a_binding() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    missing_binding = _review_again(
        replace(draft, bindings=(draft.bindings[0],)), "review-missing-binding"
    )
    assert validate_draft(missing_binding).failure.code is ValidationFailureCode.INVALID_ARITY


@pytest.mark.parametrize("field", ("schema_version", "validation_method"))
def test_unknown_draft_metadata_fails_closed(field: str) -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    unknown = _review_again(replace(draft, **{field: "unknown-metadata"}), f"review-{field}")
    assert validate_draft(unknown).failure.code is ValidationFailureCode.UNSUPPORTED_METADATA


def test_unknown_review_fingerprint_algorithm_fails_closed() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    unknown = replace(draft.semantic_review, fingerprint_algorithm="unknown-algorithm")
    assert (
        validate_draft(replace(draft, semantic_review=unknown)).failure.code
        is ValidationFailureCode.UNSUPPORTED_METADATA
    )


def test_intra_kalshi_relationship_is_native_and_validated() -> None:
    result = validate_draft(_draft(RelationshipType.EQUIVALENCE, kalshi_only=True))
    assert result.ok
    assert all(isinstance(binding, KalshiClaimBinding) for binding in result.certificate.bindings)
    assert all(binding.raw_refs == (KALSHI_RAW,) for binding in result.certificate.bindings)


def test_completeness_and_counterexamples_fail_closed() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    incomplete = replace(
        draft,
        completeness=replace(draft.completeness, declared_complete=False),
    )
    incomplete = incomplete.with_semantic_review(
        SemanticReview.for_draft(
            incomplete,
            review_id=SemanticReviewId("review-incomplete"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(incomplete).failure.code is ValidationFailureCode.INCOMPLETE_STATE_SPACE
    bad_state = replace(
        draft.feasible_states[0],
        truth_assignments={PropositionId("p-0"): True, PropositionId("p-1"): False},
        payout_assignments={
            ClaimBindingId("b-0"): Decimal("1"),
            ClaimBindingId("b-1"): Decimal("0"),
        },
    )
    counterexample = replace(draft, feasible_states=(bad_state,) + draft.feasible_states[1:])
    reviewed = counterexample.with_semantic_review(
        SemanticReview.for_draft(
            counterexample,
            review_id=SemanticReviewId("review-counterexample"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(reviewed).failure.code is ValidationFailureCode.COUNTEREXAMPLE


def test_payout_validation_rejects_nonunit_and_inconsistent_values() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    state = draft.feasible_states[0]
    nonunit = replace(
        state,
        payout_assignments={**state.payout_assignments, ClaimBindingId("b-0"): Decimal("0.5")},
    )
    changed = replace(draft, feasible_states=(nonunit,) + draft.feasible_states[1:])
    reviewed = changed.with_semantic_review(
        SemanticReview.for_draft(
            changed,
            review_id=SemanticReviewId("review-payout"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(reviewed).failure.code is ValidationFailureCode.INVALID_PAYOUT
    with pytest.raises(DomainError):
        replace(state, payout_assignments={**state.payout_assignments, ClaimBindingId("b-0"): 0.0})


def test_arity_assignments_and_required_provenance_fail_closed() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    duplicate = RelationshipDeclaration(
        RelationshipType.IMPLICATION,
        (PropositionId("p-0"), PropositionId("p-0")),
    )
    duplicate_draft = replace(draft, proposed_relationship=duplicate)
    duplicate_draft = duplicate_draft.with_semantic_review(
        SemanticReview.for_draft(
            duplicate_draft,
            review_id=SemanticReviewId("review-duplicate"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(duplicate_draft).failure.code is ValidationFailureCode.INVALID_ARITY

    state = draft.feasible_states[0]
    missing_truth = replace(
        state,
        truth_assignments={PropositionId("p-0"): False},
    )
    missing_truth_draft = replace(
        draft, feasible_states=(missing_truth,) + draft.feasible_states[1:]
    )
    missing_truth_draft = missing_truth_draft.with_semantic_review(
        SemanticReview.for_draft(
            missing_truth_draft,
            review_id=SemanticReviewId("review-missing-truth"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert (
        validate_draft(missing_truth_draft).failure.code is ValidationFailureCode.INCOMPLETE_TRUTH
    )

    first_binding = next(iter(state.payout_assignments))
    missing_payout = replace(state, payout_assignments={first_binding: Decimal("0")})
    missing_payout_draft = replace(
        draft, feasible_states=(missing_payout,) + draft.feasible_states[1:]
    )
    missing_payout_draft = missing_payout_draft.with_semantic_review(
        SemanticReview.for_draft(
            missing_payout_draft,
            review_id=SemanticReviewId("review-missing-payout"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert (
        validate_draft(missing_payout_draft).failure.code is ValidationFailureCode.INCOMPLETE_PAYOUT
    )

    no_provenance = replace(draft, evidence_provenance=())
    no_provenance = no_provenance.with_semantic_review(
        SemanticReview.for_draft(
            no_provenance,
            review_id=SemanticReviewId("review-no-provenance"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="updated synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(no_provenance).failure.code is ValidationFailureCode.MISSING_PROVENANCE


def test_naive_review_time_and_float_payout_are_rejected() -> None:
    with pytest.raises(DomainError):
        SemanticReview(
            SemanticReviewId("review-naive"),
            "reviewer",
            ReviewDecision.APPROVED,
            datetime(2023, 1, 1),
            "basis",
            "synthetic-fixture-only",
            "0" * 64,
        )
    with pytest.raises(DomainError):
        FeasibleState(
            FeasibleStateId("float-state"),
            TerminalStateKind.NORMAL,
            {PropositionId("p"): True},
            {ClaimBindingId("b"): 1.0},
        )


def test_legacy_threshold_serialization_and_review_fingerprint_are_unchanged() -> None:
    assert stable_json_bytes(Threshold("threshold", Decimal("10"), "units")) == (
        b'{"name":"threshold","unit":"units","value":"10"}'
    )
    assert reviewable_fingerprint(_draft(RelationshipType.IMPLICATION)) == (
        "5f0bcc7170f1dc44f490587d29da75d7c4020db2fedfaa04da618d3470eb3683"
    )


def test_only_approved_milestone_2_packages_exist() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "invariant_engine"
    assert (root / "opportunities").exists()
    for prohibited in (
        "diagnostics",
        "simulation",
        "risk",
        "execution",
        "reconciliation",
    ):
        assert not (root / prohibited).exists()


def test_terminal_states_are_retained_and_participate() -> None:
    draft = _draft(
        RelationshipType.IMPLICATION,
        terminal_kinds=(
            TerminalStateKind.NORMAL,
            TerminalStateKind.CANCELLATION,
            TerminalStateKind.VOID,
            TerminalStateKind.REFUND,
        ),
    )
    refund_state = replace(
        draft.feasible_states[0],
        state_id=FeasibleStateId("s-refund"),
        terminal_kind=TerminalStateKind.REFUND,
    )
    draft = _review_again(
        replace(draft, feasible_states=draft.feasible_states + (refund_state,)),
        "review-terminal-states",
    )
    assert {state.terminal_kind for state in draft.feasible_states} == {
        TerminalStateKind.NORMAL,
        TerminalStateKind.CANCELLATION,
        TerminalStateKind.VOID,
        TerminalStateKind.REFUND,
    }
    result = validate_draft(draft)
    assert result.ok
    assert b'"terminal_kind":"cancellation"' in stable_json_bytes(result.certificate)


def test_conditional_and_scalar_inputs_are_explicitly_unsupported() -> None:
    conditional = _draft(RelationshipType.IMPLICATION)
    conditional_declaration = RelationshipDeclaration(
        RelationshipType.CONDITIONAL,
        conditional.proposed_relationship.proposition_ids,
        condition="if another event occurs",
    )
    conditional = replace(conditional, proposed_relationship=conditional_declaration)
    conditional = conditional.with_semantic_review(
        SemanticReview.for_draft(
            conditional,
            review_id=SemanticReviewId("review-conditional"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(conditional).failure.code is ValidationFailureCode.UNSUPPORTED_CONDITIONAL

    scalar = _draft(RelationshipType.IMPLICATION)
    scalar_binding = replace(scalar.bindings[0], classification=ClaimClassification.SCALAR)
    scalar = replace(scalar, bindings=(scalar_binding,) + scalar.bindings[1:])
    scalar = scalar.with_semantic_review(
        SemanticReview.for_draft(
            scalar,
            review_id=SemanticReviewId("review-scalar"),
            reviewer="reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="synthetic review",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(scalar).failure.code is ValidationFailureCode.UNSUPPORTED_SCALAR


def test_cross_venue_identity_and_ordered_provenance_are_preserved() -> None:
    result = validate_draft(_draft(RelationshipType.IMPLICATION, cross_venue=True))
    assert result.ok
    assert isinstance(result.certificate.bindings[0], PolymarketClaimBinding)
    assert isinstance(result.certificate.bindings[1], KalshiClaimBinding)
    assert result.certificate.bindings[0].raw_refs == (POLY_RAW,)
    assert result.certificate.bindings[1].raw_refs == (KALSHI_RAW,)
    assert result.certificate.evidence_provenance == (KALSHI_RAW, POLY_RAW)


def test_repeated_validation_and_serialization_are_byte_stable() -> None:
    draft = _draft(RelationshipType.EQUIVALENCE)
    first = validate_draft(draft)
    second = validate_draft(draft)
    assert first.ok and second.ok
    assert stable_json_bytes(first.certificate) == stable_json_bytes(second.certificate)


def test_distinct_approved_reviews_produce_distinct_certificate_identity() -> None:
    first_draft = _draft(RelationshipType.EQUIVALENCE)
    second_review = SemanticReview.for_draft(
        first_draft,
        review_id=SemanticReviewId("review-second"),
        reviewer="another-reviewer",
        decision=ReviewDecision.APPROVED,
        reviewed_at=datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC),
        basis="A distinct approved synthetic review.",
        authority_scope="synthetic-fixture-only",
    )
    second_draft = first_draft.with_semantic_review(second_review)
    first = validate_draft(first_draft)
    second = validate_draft(second_draft)
    assert first.ok and second.ok
    assert first.certificate.certificate_id != second.certificate.certificate_id
    assert stable_json_bytes(first.certificate) != stable_json_bytes(second.certificate)


def test_fixture_metadata_is_synthetic_and_versioned() -> None:
    assert FIXTURE_METADATA["schema_version"] == "relationship-fixture-v1"
    assert FIXTURE_METADATA["synthetic"] is True
    assert len(FIXTURE_METADATA["supported_relationship_types"]) == 8
    polymarket = FIXTURE_METADATA["examples"]["polymarket"]
    kalshi = FIXTURE_METADATA["examples"]["kalshi"]
    assert polymarket["market"] == _draft(RelationshipType.IMPLICATION).bindings[0].market.value
    assert (
        kalshi["market_ticker"]
        == _draft(RelationshipType.EQUIVALENCE, kalshi_only=True).bindings[0].market.market_ticker
    )


def test_relationship_validation_has_no_network_path(monkeypatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("relationship validation attempted an outbound socket")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    assert validate_draft(_draft(RelationshipType.IMPLICATION)).ok
