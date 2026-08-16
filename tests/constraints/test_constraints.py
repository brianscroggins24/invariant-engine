import gc
import json
import os
import socket
import subprocess
import sys
import weakref
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from pathlib import Path

import pytest

from invariant_engine.constraints import (
    CompilationFailureCode,
    ConstraintEvaluationStatus,
    ConstraintRelation,
    EvaluationFailureCode,
    ObservationFailureCode,
    compile_certificate,
    evaluate_constraint,
    is_trusted_constraint,
    is_trusted_observation,
    observe_kalshi,
    observe_polymarket,
    verify_constraint,
)
from invariant_engine.constraints import models as constraint_models
from invariant_engine.domain.ids import (
    ContractReference,
    FixtureReference,
    MarketReference,
    RawReference,
    Venue,
)
from invariant_engine.domain.order_book import PriceLevel
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.provenance import RawEnvelope, SourceType
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
    RelationshipCertificateDraft,
    RelationshipDeclaration,
    RelationshipType,
    ReviewDecision,
    SemanticReview,
    SemanticReviewId,
    TerminalStateKind,
    ValidationFailureCode,
    validate_draft,
)
from invariant_engine.relationships.certificates import RelationshipCertificate
from invariant_engine.relationships.ids import CertificateId
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiMarketIdentity,
    KalshiNativeSideKind,
    KalshiPriceConvention,
)
from invariant_engine.venues.kalshi import (
    parse_snapshot as parse_kalshi_snapshot,
)
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
)
from invariant_engine.venues.polymarket import (
    parse_snapshot as parse_polymarket_snapshot,
)

UTC_TIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
CONSTRAINT_CASES = json.loads((FIXTURES / "constraints" / "cases.json").read_text(encoding="utf-8"))
SUPPORTED_CASES = tuple(CONSTRAINT_CASES["cases"]["supported_relationships"])
POLY_RAW = RawReference("poly-raw", Venue.POLYMARKET)
KALSHI_RAW = RawReference("kalshi-raw", Venue.KALSHI)


class _RaisingTimezone(tzinfo):
    def utcoffset(self, _dt):
        raise RuntimeError("synthetic timezone failure")

    def dst(self, _dt):
        return timedelta(0)


class _NoneTimezone(tzinfo):
    def utcoffset(self, _dt):
        return None

    def dst(self, _dt):
        return None


BAD_TIMESTAMPS = (
    pytest.param(
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=14))),
        id="utc-overflow",
    ),
    pytest.param(datetime(2023, 11, 14, tzinfo=_RaisingTimezone()), id="utcoffset-raises"),
    pytest.param(datetime(2023, 11, 14, tzinfo=_NoneTimezone()), id="utcoffset-none"),
)


def _binding(proposition: Proposition, index: int, *, kalshi: bool = False):
    binding_id = ClaimBindingId(f"b-{index}")
    if kalshi:
        return KalshiClaimBinding(
            proposition_id=proposition.proposition_id,
            binding_id=binding_id,
            classification=ClaimClassification.BINARY_UNIT,
            market=KalshiMarketIdentity("SYNTHETIC-EVENT-MARKET", "synthetic-kalshi-market-id"),
            native_side=KalshiNativeSideKind.YES,
            evidence_ids=(EvidenceId("e-rule"),),
            raw_refs=(KALSHI_RAW,),
        )
    return PolymarketClaimBinding(
        proposition_id=proposition.proposition_id,
        binding_id=binding_id,
        classification=ClaimClassification.BINARY_UNIT,
        market=MarketReference("0xsynthetic-polymarket-market", Venue.POLYMARKET),
        outcome_token=ContractReference("synthetic-polymarket-yes-token", Venue.POLYMARKET),
        evidence_ids=(EvidenceId("e-rule"),),
        raw_refs=(POLY_RAW,),
    )


def _vectors(relationship: RelationshipType, count: int) -> tuple[tuple[bool, ...], ...]:
    if relationship in {RelationshipType.IMPLICATION, RelationshipType.SUBSET}:
        return ((False, False), (False, True), (True, True))
    if relationship is RelationshipType.SUPERSET:
        return ((False, False), (True, False), (True, True))
    if relationship is RelationshipType.EQUIVALENCE:
        return ((False, False), (True, True))
    if relationship is RelationshipType.COMPLEMENT:
        return ((True, False), (False, True))
    if relationship is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        return ((False,) * count,) + tuple(
            tuple(index == member for index in range(count)) for member in range(count)
        )
    if relationship in {
        RelationshipType.EXHAUSTIVE_SET,
        RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
    }:
        return tuple(tuple(index == member for index in range(count)) for member in range(count))
    raise AssertionError(relationship)


def _draft(
    relationship: RelationshipType,
    *,
    count: int = 2,
    kalshi: bool = False,
    terminal_kinds: tuple[TerminalStateKind, ...] = (TerminalStateKind.NORMAL,),
) -> RelationshipCertificateDraft:
    propositions = tuple(
        Proposition(PropositionId(f"p-{index}"), f"Synthetic proposition {index}")
        for index in range(count)
    )
    declaration = RelationshipDeclaration(
        relationship, tuple(item.proposition_id for item in propositions)
    )
    bindings = tuple(
        _binding(proposition, index, kalshi=kalshi)
        for index, proposition in enumerate(propositions)
    )
    raw_refs = (KALSHI_RAW,) if kalshi else (POLY_RAW,)
    evidence = Evidence(
        EvidenceId("e-rule"),
        EvidenceKind.MARKET_RULE,
        rule_text="Synthetic rule text.",
        locator="fixtures/constraints/README.md#synthetic",
        raw_refs=raw_refs,
        synthetic=True,
    )
    states = []
    for state_index, vector in enumerate(_vectors(relationship, count)):
        truth = {
            proposition.proposition_id: vector[index]
            for index, proposition in enumerate(propositions)
        }
        states.append(
            FeasibleState(
                FeasibleStateId(f"s-{state_index}"),
                terminal_kinds[state_index % len(terminal_kinds)],
                truth,
                {
                    binding.binding_id: Decimal("1")
                    if truth[binding.proposition_id]
                    else Decimal("0")
                    for binding in bindings
                },
                evidence_ids=(EvidenceId("e-rule"),),
                raw_refs=raw_refs,
            )
        )
    draft = RelationshipCertificateDraft(
        draft_id=DraftId(f"draft-{relationship.value}"),
        originating_candidate_id=CandidateId("candidate-constraints"),
        propositions=propositions,
        bindings=bindings,
        proposed_relationship=declaration,
        evidence=(evidence,),
        event_scope="synthetic event",
        thresholds=(),
        observation_period=None,
        close_time=UTC_TIME,
        resolution_time=UTC_TIME,
        resolution_sources=(EvidenceId("e-rule"),),
        cancellation_behavior="modeled",
        void_behavior="modeled",
        refund_behavior="modeled",
        payout_structure="unit binary payout",
        edge_cases=(),
        assumptions=("synthetic only",),
        uncertainties=("not production authority",),
        evidence_provenance=raw_refs,
        validation_method="truth-payoff-exhaustive-supplied-v1",
        feasible_states=tuple(states),
        completeness=CompletenessDeclaration(
            True,
            "Synthetic supplied state space only.",
            "synthetic-fixture-only",
            evidence_ids=(EvidenceId("e-rule"),),
            raw_refs=raw_refs,
        ),
    )
    return draft.with_semantic_review(
        SemanticReview.for_draft(
            draft,
            review_id=SemanticReviewId("review-constraints"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic fixture review only.",
            authority_scope="synthetic-fixture-only",
        )
    )


def _envelope(path: Path, venue: Venue, schema: str, *, timestamp: bool = False):
    payload = path.read_bytes()
    if timestamp and venue is Venue.KALSHI:
        import json

        value = json.loads(payload.decode("utf-8"))
        value["msg"]["ts"] = "2023-11-14T22:13:20Z"
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return RawEnvelope.from_fixture_bytes(
        venue=venue,
        fixture=FixtureReference(path.name, venue),
        data=payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://constraints",
        capture_timestamp=UTC_TIME,
        schema_version=schema,
    )


def _snapshots():
    poly = parse_polymarket_snapshot(
        _envelope(
            FIXTURES / "polymarket" / "orderbook_snapshot.json",
            Venue.POLYMARKET,
            POLYMARKET_DIRECT_SCHEMA_VERSION,
        )
    )
    kalshi = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            KALSHI_ORDERBOOK_SCHEMA_VERSION,
            timestamp=True,
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    return poly, kalshi


def _polymarket_quote_snapshot(snapshot, bid: Decimal, ask: Decimal):
    order_book = replace(
        snapshot.order_book,
        bids=replace(
            snapshot.order_book.bids,
            levels=(PriceLevel(bid, Decimal("1")),),
        ),
        asks=replace(
            snapshot.order_book.asks,
            levels=(PriceLevel(ask, Decimal("1")),),
        ),
    )
    return replace(snapshot, order_book=order_book)


def _tamper_dataclass(value, **changes):
    clone = object.__new__(type(value))
    for field in fields(type(value)):
        object.__setattr__(clone, field.name, changes.get(field.name, getattr(value, field.name)))
    return clone


def _tampered_certificate(certificate: RelationshipCertificate, **changes):
    return _tamper_dataclass(certificate, **changes)


@pytest.mark.parametrize("case", SUPPORTED_CASES, ids=lambda item: item["label"])
def test_all_supported_relationships_compile(case) -> None:
    relationship = RelationshipType(case["relationship"])
    count = case["count"]
    result = compile_certificate(validate_draft(_draft(relationship, count=count)).certificate)
    assert result.ok, result.failures
    assert result.constraint is not None
    assert result.constraint.relation.value == case["relation"]
    assert result.constraint.bound == Decimal(case["bound"])
    assert tuple(term.coefficient for term in result.constraint.terms) == tuple(
        Decimal(value) for value in case["coefficients"]
    )
    assert tuple(term.proposition_id.value for term in result.constraint.terms) == tuple(
        f"p-{index}" for index in range(count)
    )


def test_compiler_rejects_candidate_draft_and_arbitrary_object() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    candidate = RelationshipCandidate(
        CandidateId("candidate-only"),
        draft.proposed_relationship.proposition_ids,
        draft.proposed_relationship,
    )
    assert compile_certificate(candidate).failure.code is CompilationFailureCode.WRONG_TYPE
    assert compile_certificate(draft).failure.code is CompilationFailureCode.WRONG_TYPE
    assert (
        compile_certificate({"certificate": "not typed"}).failure.code
        is CompilationFailureCode.WRONG_TYPE
    )


def test_conditional_and_scalar_inputs_remain_upstream_unsupported() -> None:
    conditional = _draft(RelationshipType.IMPLICATION)
    conditional = replace(
        conditional,
        proposed_relationship=RelationshipDeclaration(
            RelationshipType.IMPLICATION,
            conditional.proposed_relationship.proposition_ids,
            condition="if synthetic condition",
        ),
    )
    conditional = conditional.with_semantic_review(
        SemanticReview.for_draft(
            conditional,
            review_id=SemanticReviewId("review-conditional"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic unsupported fixture.",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(conditional).failure.code is ValidationFailureCode.UNSUPPORTED_CONDITIONAL
    assert compile_certificate(conditional).failure.code is CompilationFailureCode.WRONG_TYPE

    scalar = _draft(RelationshipType.IMPLICATION)
    scalar = replace(
        scalar,
        bindings=(
            replace(scalar.bindings[0], classification=ClaimClassification.SCALAR),
            scalar.bindings[1],
        ),
    )
    scalar = scalar.with_semantic_review(
        SemanticReview.for_draft(
            scalar,
            review_id=SemanticReviewId("review-scalar"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic unsupported fixture.",
            authority_scope="synthetic-fixture-only",
        )
    )
    assert validate_draft(scalar).failure.code is ValidationFailureCode.UNSUPPORTED_SCALAR
    assert compile_certificate(scalar).failure.code is CompilationFailureCode.WRONG_TYPE


def test_compilation_is_byte_deterministic_and_has_no_certificate_factory() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    first = compile_certificate(certificate).constraint
    second = compile_certificate(certificate).constraint
    assert first is not None and second is not None
    assert stable_json_bytes(first) == stable_json_bytes(second)
    assert first.constraint_id == second.constraint_id
    assert not hasattr(RelationshipCertificate, "_from_validated")


def test_runtime_trust_state_is_absent_from_stable_v1_schemas() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    poly, _ = _snapshots()
    observation = observe_polymarket(certificate.bindings[0], poly).observation
    assert observation is not None
    constraint_bytes = stable_json_bytes(compiled)
    observation_bytes = stable_json_bytes(observation)
    constraint_payload = json.loads(constraint_bytes)
    observation_payload = json.loads(observation_bytes)
    assert "_trusted" not in constraint_payload
    assert "_trusted" not in observation_payload
    assert {item.name for item in fields(type(compiled))} <= set(constraint_payload)
    assert {item.name for item in fields(type(observation))} <= set(observation_payload)
    assert constraint_bytes == stable_json_bytes(compiled)
    assert observation_bytes == stable_json_bytes(observation)
    assert is_trusted_constraint(compiled)
    assert is_trusted_observation(observation)
    assert not is_trusted_constraint(replace(compiled))
    assert not is_trusted_observation(replace(observation))


def test_trusted_registries_cleanup_after_produced_objects_are_collected() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    poly, _ = _snapshots()
    gc.collect()
    constraint_baseline = len(constraint_models._TRUSTED_CONSTRAINTS)
    observation_baseline = len(constraint_models._TRUSTED_OBSERVATIONS)

    def produce_trusted_values():
        compiled = compile_certificate(certificate).constraint
        observation = observe_polymarket(certificate.bindings[0], poly).observation
        assert compiled is not None and observation is not None
        assert is_trusted_constraint(compiled)
        assert is_trusted_observation(observation)
        return compiled, observation

    compiled, observation = produce_trusted_values()
    compiled_ref = weakref.ref(compiled)
    observation_ref = weakref.ref(observation)
    assert compiled_ref() is not None
    assert observation_ref() is not None
    assert is_trusted_constraint(compiled_ref())
    assert is_trusted_observation(observation_ref())
    del compiled, observation
    gc.collect()
    assert compiled_ref() is None
    assert observation_ref() is None
    assert len(constraint_models._TRUSTED_CONSTRAINTS) == constraint_baseline
    assert len(constraint_models._TRUSTED_OBSERVATIONS) == observation_baseline


def test_stale_trust_cleanup_cannot_remove_a_replacement_entry() -> None:
    class WeakReferenceable:
        pass

    old_value = WeakReferenceable()
    new_value = WeakReferenceable()
    old_reference = weakref.ref(old_value)
    new_reference = weakref.ref(new_value)
    registry: dict[int, weakref.ReferenceType[object]] = {id(old_value): new_reference}

    constraint_models._remove_trust(registry, id(old_value), old_reference)

    assert registry[id(old_value)] is new_reference


def test_certificate_integrity_closes_review_digest_id_and_validation_metadata() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    assert compile_certificate(certificate).ok
    forged_fingerprint = _tampered_certificate(certificate, validation_fingerprint="0" * 64)
    assert (
        compile_certificate(forged_fingerprint).failure.code
        is CompilationFailureCode.INVALID_CERTIFICATE
    )
    forged_id = _tampered_certificate(certificate, certificate_id=CertificateId("cert:" + "0" * 64))
    assert compile_certificate(forged_id).failure.code is CompilationFailureCode.INVALID_CERTIFICATE
    rejected_review = _tampered_certificate(
        certificate,
        semantic_review=replace(
            certificate.semantic_review,
            decision=ReviewDecision.REJECTED,
        ),
    )
    assert (
        compile_certificate(rejected_review).failure.code
        is CompilationFailureCode.INVALID_CERTIFICATE
    )
    mismatched_review = _tampered_certificate(
        certificate,
        semantic_review=replace(certificate.semantic_review, draft_fingerprint="0" * 64),
    )
    assert (
        compile_certificate(mismatched_review).failure.code
        is CompilationFailureCode.INVALID_CERTIFICATE
    )
    unsupported_method = _tampered_certificate(certificate, validation_method="unsupported")
    assert (
        compile_certificate(unsupported_method).failure.code
        is CompilationFailureCode.INVALID_CERTIFICATE
    )


def test_declaration_order_controls_terms_when_certificate_storage_is_reversed() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    reordered = replace(draft, propositions=tuple(reversed(draft.propositions)))
    reviewed = reordered.with_semantic_review(
        SemanticReview.for_draft(
            reordered,
            review_id=SemanticReviewId("review-reordered"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic reordered-storage fixture.",
            authority_scope="synthetic-fixture-only",
        )
    )
    certificate = validate_draft(reviewed).certificate
    assert certificate is not None
    assert tuple(item.proposition_id.value for item in certificate.propositions) == ("p-1", "p-0")
    result = compile_certificate(certificate)
    assert result.ok, result.failures
    assert result.constraint is not None
    assert tuple(term.proposition_id.value for term in result.constraint.terms) == ("p-0", "p-1")


def test_payoff_verifier_requires_every_certified_binding_and_complete_state_map() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    incomplete_constraint = replace(
        compiled,
        terms=(replace(compiled.terms[0], coefficient=Decimal("0")),),
        binding_identities=(compiled.binding_identities[0],),
    )
    assert not verify_constraint(incomplete_constraint, certificate).ok
    first_state = certificate.feasible_states[0]
    missing_payout = _tampered_certificate(
        certificate,
        feasible_states=(
            replace(
                first_state,
                payout_assignments={compiled.terms[0].claim_binding_id: Decimal("0")},
            ),
        ),
    )
    assert verify_constraint(compiled, missing_payout).failures[0].code.name == "INVALID_CONSTRAINT"
    extra_payout = _tampered_certificate(
        certificate,
        feasible_states=(
            replace(
                first_state,
                payout_assignments={
                    **first_state.payout_assignments,
                    ClaimBindingId("unexpected"): Decimal("0"),
                },
            ),
        ),
    )
    assert verify_constraint(compiled, extra_payout).failures[0].code.name == "INVALID_CONSTRAINT"
    nonbinary_payout = _tampered_certificate(
        certificate,
        feasible_states=(
            replace(
                first_state,
                payout_assignments={
                    compiled.terms[0].claim_binding_id: Decimal("0.5"),
                    compiled.terms[1].claim_binding_id: Decimal("0"),
                },
            ),
        ),
    )
    assert (
        verify_constraint(compiled, nonbinary_payout).failures[0].code.name == "INVALID_CONSTRAINT"
    )


def test_payoff_verifier_rejects_incorrect_constraint_parts() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None and certificate is not None
    wrong_term = replace(compiled.terms[1], coefficient=Decimal("1"))
    wrong_coefficients = replace(compiled, terms=(compiled.terms[0], wrong_term))
    assert not verify_constraint(wrong_coefficients, certificate).ok
    assert not verify_constraint(
        replace(compiled, relation=ConstraintRelation.GREATER_THAN_OR_EQUAL), certificate
    ).ok
    assert not verify_constraint(replace(compiled, bound=Decimal("-1")), certificate).ok
    assert not verify_constraint(
        replace(
            compiled,
            terms=(
                compiled.terms[0],
                replace(compiled.terms[1], claim_binding_id=ClaimBindingId("missing")),
            ),
        ),
        certificate,
    ).ok
    assert not verify_constraint(
        replace(compiled, certificate_id=CertificateId("cert:" + "0" * 64)), certificate
    ).ok


def test_polymarket_observation_uses_direct_best_levels_and_preserves_lineage() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    poly, _ = _snapshots()
    result = observe_polymarket(certificate.bindings[0], poly)
    assert result.ok and result.observation is not None
    assert result.observation.best_bid == Decimal("0.50")
    assert result.observation.best_ask == Decimal("0.55")
    assert result.observation.raw_refs == poly.raw_refs
    assert result.observation.best_bid != poly.last_trade_price


def test_polymarket_observation_fail_closed_matrix_uses_fixture_labels() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    poly, _ = _snapshots()
    labels = CONSTRAINT_CASES["cases"]["observation_failure_labels"]
    empty_bid_book = replace(poly.order_book, bids=replace(poly.order_book.bids, levels=()))
    empty_ask_book = replace(poly.order_book, asks=replace(poly.order_book.asks, levels=()))
    crossed_book = replace(
        poly.order_book,
        bids=replace(
            poly.order_book.bids,
            levels=(replace(poly.order_book.bids.levels[0], price=Decimal("0.70")),),
        ),
        asks=replace(
            poly.order_book.asks,
            levels=(replace(poly.order_book.asks.levels[0], price=Decimal("0.30")),),
        ),
    )
    cases = {
        "missing_bid": _tamper_dataclass(poly, order_book=empty_bid_book),
        "missing_ask": _tamper_dataclass(poly, order_book=empty_ask_book),
        "crossed": _tamper_dataclass(poly, order_book=crossed_book),
        "invalid_state": replace(
            poly, order_book=replace(poly.order_book, validity=StateValidity.INVALID)
        ),
        "stale": replace(
            poly,
            order_book=replace(
                poly.order_book,
                warnings=(WarningRecord(WarningCode.STALE_SNAPSHOT, "synthetic stale"),),
            ),
        ),
        "provenance": _tamper_dataclass(
            poly, order_book=_tamper_dataclass(poly.order_book, raw_refs=())
        ),
        "market_mismatch": replace(
            poly,
            order_book=replace(
                poly.order_book,
                market=MarketReference("other-market", Venue.POLYMARKET),
            ),
        ),
        "token_mismatch": replace(
            poly,
            order_book=replace(
                poly.order_book,
                contract=ContractReference("other-token", Venue.POLYMARKET),
            ),
        ),
    }
    for label, snapshot in cases.items():
        result = observe_polymarket(draft.bindings[0], snapshot)
        assert result.failure is not None
        assert result.failure.code.value == labels[label]
    schema_mismatch = _tamper_dataclass(poly, schema_version="unsupported")
    result = observe_polymarket(draft.bindings[0], schema_mismatch)
    assert result.failure is not None
    assert result.failure.code is ObservationFailureCode.UNSUPPORTED_SCHEMA


@pytest.mark.parametrize(
    ("convention", "side", "expected"),
    [
        (KalshiPriceConvention.OUTCOME_LEG, KalshiNativeSideKind.YES, ("0.25", "0.60")),
        (KalshiPriceConvention.OUTCOME_LEG, KalshiNativeSideKind.NO, ("0.40", "0.75")),
        (KalshiPriceConvention.UNIFIED_YES_LEG, KalshiNativeSideKind.YES, ("0.25", "0.60")),
        (KalshiPriceConvention.UNIFIED_YES_LEG, KalshiNativeSideKind.NO, ("0.40", "0.75")),
    ],
)
def test_kalshi_observation_uses_convention_aware_methods(convention, side, expected) -> None:
    draft = _draft(RelationshipType.IMPLICATION, kalshi=True)
    binding = replace(draft.bindings[0], native_side=side)
    snapshot_path = (
        FIXTURES / "kalshi" / "orderbook_snapshot_unified_yes.json"
        if convention is KalshiPriceConvention.UNIFIED_YES_LEG
        else FIXTURES / "kalshi" / "orderbook_snapshot.json"
    )
    snapshot = parse_kalshi_snapshot(
        _envelope(snapshot_path, Venue.KALSHI, KALSHI_ORDERBOOK_SCHEMA_VERSION, timestamp=True),
        price_convention=convention,
    )
    result = observe_kalshi(binding, snapshot)
    assert result.ok and result.observation is not None
    assert (str(result.observation.best_bid), str(result.observation.best_ask)) == expected
    assert any(warning.code is WarningCode.DERIVED_VALUE for warning in result.observation.warnings)


def test_capture_fallback_and_empty_side_are_unavailable() -> None:
    draft = _draft(RelationshipType.IMPLICATION, kalshi=True)
    fallback = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            KALSHI_ORDERBOOK_SCHEMA_VERSION,
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    assert (
        observe_kalshi(draft.bindings[0], fallback).failure.code
        is ObservationFailureCode.UNAVAILABLE_TIMESTAMP
    )
    empty = replace(fallback, yes_side=replace(fallback.yes_side, levels=()))
    result = observe_kalshi(draft.bindings[0], replace(empty, timestamp_source="venue"))
    assert result.failure.code is ObservationFailureCode.MISSING_BID


def test_kalshi_observation_fail_closed_matrix_and_derived_warning() -> None:
    draft = _draft(RelationshipType.IMPLICATION, kalshi=True)
    _, kalshi = _snapshots()
    labels = CONSTRAINT_CASES["cases"]["observation_failure_labels"]
    empty_ask = replace(kalshi, no_side=replace(kalshi.no_side, levels=()))
    wrong_market = replace(
        kalshi,
        market=KalshiMarketIdentity("OTHER-MARKET", "other-market-id"),
    )
    stale = replace(
        kalshi,
        warnings=(WarningRecord(WarningCode.STALE_SNAPSHOT, "synthetic stale"),),
    )
    missing_provenance = _tamper_dataclass(kalshi, raw_refs=())
    cases = {
        "missing_ask": empty_ask,
        "market_mismatch": wrong_market,
        "stale": stale,
        "provenance": missing_provenance,
    }
    for label, snapshot in cases.items():
        result = observe_kalshi(draft.bindings[0], snapshot)
        assert result.failure is not None
        assert result.failure.code.value == labels[label]
    unsupported = _tamper_dataclass(kalshi, price_convention="unsupported")
    result = observe_kalshi(draft.bindings[0], unsupported)
    assert result.failure is not None
    assert result.failure.code is ObservationFailureCode.UNSUPPORTED_CONVENTION
    valid = observe_kalshi(draft.bindings[0], kalshi)
    assert valid.ok and valid.observation is not None
    assert any(warning.code is WarningCode.DERIVED_VALUE for warning in valid.observation.warnings)


def test_all_terminal_state_kinds_are_verified() -> None:
    kinds = tuple(
        TerminalStateKind(item) for item in CONSTRAINT_CASES["cases"]["terminal_state_kinds"]
    )
    draft = _draft(
        RelationshipType.MUTUALLY_EXCLUSIVE_SET,
        count=3,
        terminal_kinds=kinds,
    )
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    assert tuple(state.terminal_kind for state in certificate.feasible_states) == (
        TerminalStateKind.NORMAL,
        TerminalStateKind.CANCELLATION,
        TerminalStateKind.VOID,
        TerminalStateKind.REFUND,
    )
    assert compile_certificate(certificate).ok


def test_evaluator_returns_interval_statuses_and_exact_timestamp_behavior() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    observations = tuple(
        observe_polymarket(binding, poly).observation for binding in certificate.bindings
    )
    assert all(item is not None for item in observations)
    valid = evaluate_constraint(constraint, observations)
    assert valid.evaluation is not None
    assert valid.evaluation.status is ConstraintEvaluationStatus.INDETERMINATE
    assert valid.evaluation.minimum_lhs == Decimal("-0.05")
    assert valid.evaluation.maximum_lhs == Decimal("0.05")
    assert valid.evaluation.common_timestamp == UTC_TIME

    shifted_snapshot = replace(
        poly,
        order_book=replace(
            poly.order_book,
            timestamp=UTC_TIME.replace(second=21),
        ),
    )
    shifted = observe_polymarket(certificate.bindings[1], shifted_snapshot).observation
    assert shifted is not None
    unavailable = evaluate_constraint(constraint, (observations[0], shifted))
    assert unavailable.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert unavailable.evaluation is not None
    assert unavailable.evaluation.minimum_lhs is None
    assert unavailable.evaluation.maximum_lhs is None
    assert unavailable.evaluation.failures[0].code is EvaluationFailureCode.UNSYNCHRONIZED


def test_evaluator_closes_identity_and_provenance_and_keeps_violation_non_actionable() -> None:
    certificate = validate_draft(_draft(RelationshipType.COMPLEMENT)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    first = observe_polymarket(
        certificate.bindings[0], _polymarket_quote_snapshot(poly, Decimal("0.10"), Decimal("0.10"))
    ).observation
    second = observe_polymarket(
        certificate.bindings[1], _polymarket_quote_snapshot(poly, Decimal("0.10"), Decimal("0.10"))
    ).observation
    assert first is not None and second is not None
    violated = evaluate_constraint(
        constraint,
        (
            first,
            second,
        ),
    )
    assert violated.status is ConstraintEvaluationStatus.VIOLATED
    assert violated.evaluation is not None
    assert not hasattr(violated.evaluation, "opportunity_id")
    assert violated.evaluation.combined_provenance[:1] == constraint.certificate_provenance
    duplicate = evaluate_constraint(constraint, (first, first, second))
    assert duplicate.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert duplicate.evaluation is not None
    assert duplicate.evaluation.failures[0].code is EvaluationFailureCode.DUPLICATE_OBSERVATION


def test_altered_compiled_constraint_is_not_evaluable() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    altered = replace(compiled, relation=ConstraintRelation.GREATER_THAN_OR_EQUAL)
    poly, _ = _snapshots()
    observations = tuple(
        observe_polymarket(binding, poly).observation for binding in certificate.bindings
    )
    result = evaluate_constraint(altered, observations)
    assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert result.evaluation is None
    assert result.failures[0].code is EvaluationFailureCode.INVALID_CONSTRAINT


def test_altered_observation_with_original_id_is_not_evaluable() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    poly, _ = _snapshots()
    first = observe_polymarket(certificate.bindings[0], poly).observation
    second = observe_polymarket(certificate.bindings[1], poly).observation
    assert first is not None and second is not None
    altered = _tamper_dataclass(first, best_bid=Decimal("0.01"))
    result = evaluate_constraint(compiled, (altered, second))
    assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert result.evaluation is not None
    assert result.evaluation.failures[0].code is EvaluationFailureCode.INVALID_OBSERVATION


def _status_observations(certificate, snapshot, label: str):
    if label.startswith("equal-"):
        ranges = {
            "equal-satisfied": (Decimal("0.40"), Decimal("0.40"), Decimal("0.60"), Decimal("0.60")),
            "equal-zero-width-boundary-satisfied": (
                Decimal("0.40"),
                Decimal("0.40"),
                Decimal("0.60"),
                Decimal("0.60"),
            ),
            "equal-violated": (Decimal("0.80"), Decimal("0.80"), Decimal("0.80"), Decimal("0.80")),
            "equal-indeterminate": (
                Decimal("0.40"),
                Decimal("0.60"),
                Decimal("0.40"),
                Decimal("0.60"),
            ),
            "equal-one-endpoint-boundary-indeterminate": (
                Decimal("0.40"),
                Decimal("0.40"),
                Decimal("0.60"),
                Decimal("0.80"),
            ),
        }
        values = ranges[label]
    elif label.startswith("greater-"):
        ranges = {
            "greater-than-satisfied": (
                Decimal("0.80"),
                Decimal("0.80"),
                Decimal("0.10"),
                Decimal("0.10"),
            ),
            "greater-than-boundary-satisfied": (
                Decimal("0.40"),
                Decimal("0.80"),
                Decimal("0.40"),
                Decimal("0.40"),
            ),
            "greater-than-violated": (
                Decimal("0.10"),
                Decimal("0.10"),
                Decimal("0.80"),
                Decimal("0.80"),
            ),
            "greater-than-indeterminate": (
                Decimal("0.10"),
                Decimal("0.40"),
                Decimal("0.20"),
                Decimal("0.30"),
            ),
        }
        values = ranges[label]
    else:
        ranges = {
            "less-than-satisfied": (
                Decimal("0.10"),
                Decimal("0.10"),
                Decimal("0.50"),
                Decimal("0.50"),
            ),
            "less-than-boundary-satisfied": (
                Decimal("0.20"),
                Decimal("0.40"),
                Decimal("0.40"),
                Decimal("0.60"),
            ),
            "less-than-violated": (
                Decimal("0.80"),
                Decimal("0.80"),
                Decimal("0.10"),
                Decimal("0.10"),
            ),
            "less-than-indeterminate": (
                Decimal("0.10"),
                Decimal("0.40"),
                Decimal("0.20"),
                Decimal("0.30"),
            ),
        }
        values = ranges[label]
    first_snapshot = _polymarket_quote_snapshot(snapshot, values[0], values[1])
    second_snapshot = _polymarket_quote_snapshot(snapshot, values[2], values[3])
    first = observe_polymarket(certificate.bindings[0], first_snapshot).observation
    second = observe_polymarket(certificate.bindings[1], second_snapshot).observation
    assert first is not None and second is not None
    return first, second


@pytest.mark.parametrize(
    "case",
    CONSTRAINT_CASES["cases"]["evaluation_statuses"],
    ids=lambda item: item["label"],
)
def test_fixture_labeled_evaluation_status_matrix(case) -> None:
    relationship = {
        "<=": RelationshipType.IMPLICATION,
        ">=": RelationshipType.SUPERSET,
        "=": RelationshipType.COMPLEMENT,
    }[case["relation"]]
    certificate = validate_draft(_draft(relationship)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    poly, _ = _snapshots()
    observations = _status_observations(certificate, poly, case["label"])
    result = evaluate_constraint(compiled, observations)
    assert result.status.value == case["status"]
    assert result.evaluation is not None
    assert result.evaluation.minimum_lhs == Decimal(case["minimum_lhs"])
    assert result.evaluation.maximum_lhs == Decimal(case["maximum_lhs"])


def test_unavailable_evaluation_has_no_expression_bounds() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    first = observe_polymarket(certificate.bindings[0], poly).observation
    assert first is not None
    result = evaluate_constraint(constraint, (first,))
    assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert result.evaluation is not None
    assert result.evaluation.minimum_lhs is None
    assert result.evaluation.maximum_lhs is None


def test_evaluator_fail_closed_matrix_uses_fixture_labels() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    first = observe_polymarket(certificate.bindings[0], poly).observation
    second = observe_polymarket(certificate.bindings[1], poly).observation
    assert first is not None and second is not None
    labels = CONSTRAINT_CASES["cases"]["failure_labels"]
    cases = {
        "missing_observation": (first,),
        "duplicate_observation": (first, first, second),
        "identity_mismatch": (
            observe_polymarket(
                replace(
                    certificate.bindings[0],
                    market=MarketReference("other", Venue.POLYMARKET),
                ),
                replace(
                    poly,
                    order_book=replace(
                        poly.order_book,
                        market=MarketReference("other", Venue.POLYMARKET),
                    ),
                ),
            ).observation,
            second,
        ),
        "invalid_observation": (
            _tamper_dataclass(first, best_bid=Decimal("1.5")),
            second,
        ),
        "missing_provenance": (
            _tamper_dataclass(first, raw_refs=()),
            second,
        ),
        "unsynchronized": (
            first,
            observe_polymarket(
                certificate.bindings[1],
                replace(
                    poly,
                    order_book=replace(
                        poly.order_book,
                        timestamp=UTC_TIME.replace(second=21),
                    ),
                ),
            ).observation,
        ),
    }
    for label, observations in cases.items():
        result = evaluate_constraint(constraint, observations)
        assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
        assert result.evaluation is not None
        expected_failure = labels[label]
        if label in {"missing_provenance", "invalid_observation"}:
            expected_failure = "invalid_observation"
        assert result.evaluation.failures[0].code.value == expected_failure
        assert result.evaluation.minimum_lhs is None
        assert result.evaluation.maximum_lhs is None
    crossed = evaluate_constraint(
        constraint,
        (
            _tamper_dataclass(first, best_bid=Decimal("0.80"), best_ask=Decimal("0.20")),
            second,
        ),
    )
    assert crossed.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert crossed.evaluation is not None
    assert crossed.evaluation.failures[0].code.value == "invalid_observation"


def test_unexpected_observation_failures_are_cross_process_deterministic() -> None:
    script = """
from dataclasses import replace
from invariant_engine.constraints import compile_certificate, evaluate_constraint
from invariant_engine.constraints import observe_polymarket
from invariant_engine.relationships import RelationshipType, validate_draft
from invariant_engine.relationships.ids import ClaimBindingId
from invariant_engine.serialization import stable_json_bytes
from tests.constraints.test_constraints import _draft, _snapshots

certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
constraint = compile_certificate(certificate).constraint
poly, _ = _snapshots()
first = observe_polymarket(certificate.bindings[0], poly).observation
second = observe_polymarket(certificate.bindings[1], poly).observation
unexpected_a = observe_polymarket(
    replace(certificate.bindings[0], binding_id=ClaimBindingId('unexpected-a')), poly
).observation
unexpected_b = observe_polymarket(
    replace(certificate.bindings[1], binding_id=ClaimBindingId('unexpected-b')), poly
).observation
result = evaluate_constraint(constraint, (unexpected_b, unexpected_a))
print(stable_json_bytes(result.evaluation).decode())
"""
    outputs = []
    for seed in ("1", "2", "random"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = os.pathsep.join(
            (
                str(Path(__file__).resolve().parents[2] / "src"),
                str(Path(__file__).resolve().parents[2]),
            )
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
    assert '"unexpected-a"' in outputs[0]
    assert outputs[0].index("unexpected-b") < outputs[0].index("unexpected-a")


def test_warning_and_invalid_state_fail_closed_without_dropping_unrelated_warning() -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    poly, _ = _snapshots()
    warning = WarningRecord(WarningCode.DERIVED_VALUE, "retained synthetic warning")
    warned = replace(
        poly,
        order_book=replace(
            poly.order_book,
            warnings=(warning, WarningRecord(WarningCode.STALE_SNAPSHOT, "explicit stale")),
        ),
    )
    result = observe_polymarket(draft.bindings[0], warned)
    assert result.failure.code is ObservationFailureCode.STALE
    invalid = replace(poly, order_book=replace(poly.order_book, validity=StateValidity.INVALID))
    assert (
        observe_polymarket(draft.bindings[0], invalid).failure.code
        is ObservationFailureCode.INVALID_STATE
    )
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    first = observe_polymarket(certificate.bindings[0], poly).observation
    second = observe_polymarket(certificate.bindings[1], poly).observation
    assert first is not None and second is not None
    malformed_warning = _tamper_dataclass(first, warnings=("malformed",))
    malformed_timestamp = _tamper_dataclass(first, timestamp_source=object())
    for malformed in (malformed_warning, malformed_timestamp):
        result = evaluate_constraint(constraint, (malformed, second))
        assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
        assert result.evaluation is not None
        assert result.evaluation.failures[0].code is EvaluationFailureCode.INVALID_OBSERVATION


@pytest.mark.parametrize("bad_timestamp", BAD_TIMESTAMPS)
def test_polymarket_timestamp_failures_are_structured(bad_timestamp: datetime) -> None:
    draft = _draft(RelationshipType.IMPLICATION)
    poly, _ = _snapshots()
    malformed_book = _tamper_dataclass(poly.order_book, timestamp=bad_timestamp)
    malformed_snapshot = _tamper_dataclass(poly, order_book=malformed_book)
    result = observe_polymarket(draft.bindings[0], malformed_snapshot)
    assert result.observation is None
    assert result.failure is not None
    assert result.failure.code is ObservationFailureCode.UNAVAILABLE_TIMESTAMP


@pytest.mark.parametrize("bad_timestamp", BAD_TIMESTAMPS)
def test_kalshi_timestamp_failures_are_structured(bad_timestamp: datetime) -> None:
    draft = _draft(RelationshipType.IMPLICATION, kalshi=True)
    _, kalshi = _snapshots()
    malformed_snapshot = _tamper_dataclass(kalshi, timestamp=bad_timestamp)
    result = observe_kalshi(draft.bindings[0], malformed_snapshot)
    assert result.observation is None
    assert result.failure is not None
    assert result.failure.code is ObservationFailureCode.UNAVAILABLE_TIMESTAMP


@pytest.mark.parametrize("bad_timestamp", BAD_TIMESTAMPS)
def test_certificate_timestamp_failures_are_structured(bad_timestamp: datetime) -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    altered = _tampered_certificate(certificate, close_time=bad_timestamp)
    compiled = compile_certificate(altered)
    assert compiled.constraint is None
    assert compiled.failure is not None
    assert compiled.failure.code is CompilationFailureCode.INVALID_CERTIFICATE
    original_constraint = compile_certificate(certificate).constraint
    assert original_constraint is not None
    verification = verify_constraint(original_constraint, altered)
    assert not verification.ok
    assert verification.failures[0].code.name == "INVALID_CONSTRAINT"


@pytest.mark.parametrize("bad_timestamp", BAD_TIMESTAMPS)
def test_evaluation_timestamp_failures_are_unavailable(bad_timestamp: datetime) -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    first = observe_polymarket(certificate.bindings[0], poly).observation
    second = observe_polymarket(certificate.bindings[1], poly).observation
    assert first is not None and second is not None
    malformed = _tamper_dataclass(first, timestamp=bad_timestamp)
    result = evaluate_constraint(constraint, (malformed, second))
    assert result.status is ConstraintEvaluationStatus.UNAVAILABLE
    assert result.evaluation is not None
    assert result.evaluation.minimum_lhs is None
    assert result.evaluation.maximum_lhs is None


def test_cross_venue_evaluation_keeps_native_identities_and_ordered_provenance() -> None:
    base = _draft(RelationshipType.IMPLICATION)
    kalshi_binding = _binding(base.propositions[1], 1, kalshi=True)
    both_raw_refs = (POLY_RAW, KALSHI_RAW)
    states = tuple(replace(state, raw_refs=both_raw_refs) for state in base.feasible_states)
    draft = replace(
        base,
        bindings=(base.bindings[0], kalshi_binding),
        evidence=(replace(base.evidence[0], raw_refs=both_raw_refs),),
        feasible_states=states,
        evidence_provenance=both_raw_refs,
        completeness=replace(base.completeness, raw_refs=both_raw_refs),
        semantic_review=None,
    ).with_semantic_review(
        SemanticReview.for_draft(
            replace(
                base,
                bindings=(base.bindings[0], kalshi_binding),
                evidence=(replace(base.evidence[0], raw_refs=both_raw_refs),),
                feasible_states=states,
                evidence_provenance=both_raw_refs,
                completeness=replace(base.completeness, raw_refs=both_raw_refs),
                semantic_review=None,
            ),
            review_id=SemanticReviewId("review-cross-venue"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic cross-venue fixture only.",
            authority_scope="synthetic-fixture-only",
        )
    )
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, kalshi = _snapshots()
    poly_observation = observe_polymarket(certificate.bindings[0], poly).observation
    kalshi_observation = observe_kalshi(certificate.bindings[1], kalshi).observation
    assert poly_observation is not None and kalshi_observation is not None
    result = evaluate_constraint(constraint, (kalshi_observation, poly_observation))
    assert result.status is ConstraintEvaluationStatus.INDETERMINATE
    assert result.evaluation is not None
    assert tuple(item.venue for item in constraint.binding_identities) == (
        Venue.POLYMARKET,
        Venue.KALSHI,
    )
    assert result.evaluation.combined_provenance[:2] == both_raw_refs
    assert result.evaluation.observation_provenance[-1].venue is Venue.KALSHI


def test_equal_instants_with_different_offsets_are_accepted() -> None:
    certificate = validate_draft(_draft(RelationshipType.IMPLICATION)).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    poly, _ = _snapshots()
    first = observe_polymarket(certificate.bindings[0], poly).observation
    offset_snapshot = replace(
        poly,
        order_book=replace(
            poly.order_book,
            timestamp=UTC_TIME.astimezone(timezone(timedelta(hours=-5))),
        ),
    )
    second = observe_polymarket(certificate.bindings[1], offset_snapshot).observation
    assert first is not None and second is not None
    result = evaluate_constraint(
        constraint,
        (first, second),
    )
    assert result.status is ConstraintEvaluationStatus.INDETERMINATE
    assert result.evaluation is not None
    assert result.evaluation.common_timestamp == UTC_TIME


def test_constraint_boundary_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("constraint boundary attempted network access")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    certificate = validate_draft(_draft(RelationshipType.COMPLEMENT)).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate)
    assert compiled.ok
    poly, _ = _snapshots()
    observations = tuple(
        observe_polymarket(binding, poly).observation for binding in certificate.bindings
    )
    assert evaluate_constraint(compiled.constraint, observations).evaluation is not None
