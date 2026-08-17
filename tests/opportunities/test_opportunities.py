"""Adversarial tests for the bounded historical economics boundary."""

import copy
import gc
import json
import os
import pickle
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from invariant_engine.constraints import (
    ConstraintEvaluationStatus,
    compile_certificate,
    evaluate_constraint,
    observe_polymarket,
)
from invariant_engine.domain.ids import (
    ContractReference,
    FixtureReference,
    MarketReference,
    RawReference,
    Venue,
)
from invariant_engine.domain.order_book import BookSide, BookSideKind, PriceLevel
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.opportunities import (
    DecimalInterval,
    FeeCalculationScope,
    FeeFormulaKind,
    FeePolicy,
    FeePolicyAssignment,
    FeeRole,
    FeeRoundingScope,
    FeeTradeSide,
    OpportunityEconomicsStatus,
    OpportunityReasonCode,
    evaluate_opportunity,
    is_trusted_candidate,
)
from invariant_engine.opportunities.evaluator import _round
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
    validate_draft,
)
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiMarketIdentity,
    KalshiNativeBookSide,
    KalshiNativeSideKind,
    KalshiOrderBookSnapshot,
    KalshiPriceConvention,
)
from invariant_engine.venues.kalshi import parse_snapshot as parse_kalshi_snapshot
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
    PolymarketOrderBookSnapshot,
)
from invariant_engine.venues.polymarket import (
    parse_snapshot as parse_polymarket_snapshot,
)

UTC_TIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
POLY_RAW = RawReference("certificate-poly", Venue.POLYMARKET)
KALSHI_RAW = RawReference("certificate-kalshi", Venue.KALSHI)


def _vectors(relationship: RelationshipType, count: int) -> tuple[tuple[bool, ...], ...]:
    if relationship is RelationshipType.COMPLEMENT:
        return ((True, False), (False, True))
    if relationship is RelationshipType.EXHAUSTIVE_SET:
        return tuple(tuple(index == member for index in range(count)) for member in range(count))
    if relationship is RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION:
        return tuple(tuple(index == member for index in range(count)) for member in range(count))
    if relationship is RelationshipType.IMPLICATION:
        return ((False, False), (False, True), (True, True))
    if relationship is RelationshipType.EQUIVALENCE:
        return ((False, False), (True, True))
    if relationship is RelationshipType.SUBSET:
        return ((False, False), (False, True), (True, True))
    if relationship is RelationshipType.SUPERSET:
        return ((False, False), (True, False), (True, True))
    if relationship is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        return ((False,) * count,) + tuple(
            tuple(index == member for index in range(count)) for member in range(count)
        )
    raise AssertionError(relationship)


def _draft(
    relationship: RelationshipType,
    *,
    count: int = 2,
    kalshi: bool = False,
    kalshi_native_side: KalshiNativeSideKind = KalshiNativeSideKind.YES,
    terminal_kinds: tuple[TerminalStateKind, ...] = (TerminalStateKind.NORMAL,),
) -> RelationshipCertificateDraft:
    propositions = tuple(
        Proposition(PropositionId(f"op-p-{index}"), f"Synthetic opportunity proposition {index}")
        for index in range(count)
    )
    declaration = RelationshipDeclaration(
        relationship, tuple(item.proposition_id for item in propositions)
    )
    venue = Venue.KALSHI if kalshi else Venue.POLYMARKET
    raw_refs = tuple(
        RawReference(f"certificate-{venue.value}-{index}", venue) for index in range(count)
    )
    bindings = tuple(
        KalshiClaimBinding(
            proposition_id=item.proposition_id,
            binding_id=ClaimBindingId(f"op-b-{index}"),
            classification=ClaimClassification.BINARY_UNIT,
            market=KalshiMarketIdentity(f"OP-EVENT-MARKET-{index}", f"op-market-id-{index}"),
            native_side=kalshi_native_side,
            evidence_ids=(EvidenceId("op-rule"),),
            raw_refs=(raw_refs[index],),
        )
        if kalshi
        else PolymarketClaimBinding(
            proposition_id=item.proposition_id,
            binding_id=ClaimBindingId(f"op-b-{index}"),
            classification=ClaimClassification.BINARY_UNIT,
            market=MarketReference("op-market", Venue.POLYMARKET),
            outcome_token=ContractReference(f"op-token-{index}", Venue.POLYMARKET),
            native_outcome_side="yes",
            evidence_ids=(EvidenceId("op-rule"),),
            raw_refs=(raw_refs[index],),
        )
        for index, item in enumerate(propositions)
    )
    evidence = Evidence(
        evidence_id=EvidenceId("op-rule"),
        kind=EvidenceKind.MARKET_RULE,
        rule_text="Synthetic rule text.",
        locator="fixtures/opportunities/cases.json#synthetic",
        raw_refs=raw_refs,
        synthetic=True,
    )
    states = tuple(
        FeasibleState(
            FeasibleStateId(f"op-state-{index}"),
            terminal_kinds[index % len(terminal_kinds)],
            {item.proposition_id: vector[position] for position, item in enumerate(propositions)},
            {
                binding.binding_id: Decimal("1") if vector[position] else Decimal("0")
                for position, binding in enumerate(bindings)
            },
            evidence_ids=(EvidenceId("op-rule"),),
            raw_refs=raw_refs,
        )
        for index, vector in enumerate(_vectors(relationship, count))
    )
    candidate = RelationshipCandidate(
        CandidateId("op-candidate"),
        tuple(item.proposition_id for item in propositions),
        declaration,
        evidence_ids=(EvidenceId("op-rule"),),
        raw_refs=raw_refs,
    )
    draft = RelationshipCertificateDraft(
        draft_id=DraftId(f"op-draft-{relationship.value}"),
        originating_candidate_id=candidate.candidate_id,
        propositions=propositions,
        bindings=bindings,
        proposed_relationship=declaration,
        evidence=(evidence,),
        event_scope="synthetic opportunity event",
        thresholds=(),
        observation_period=None,
        close_time=UTC_TIME,
        resolution_time=UTC_TIME,
        resolution_sources=(EvidenceId("op-rule"),),
        cancellation_behavior="retained",
        void_behavior="retained",
        refund_behavior="retained",
        payout_structure="binary unit payout",
        edge_cases=(),
        assumptions=("synthetic only",),
        uncertainties=("not production authority",),
        evidence_provenance=raw_refs,
        validation_method="truth-payoff-exhaustive-supplied-v1",
        feasible_states=states,
        completeness=CompletenessDeclaration(
            True,
            "Synthetic supplied state space only.",
            "synthetic-fixture-only",
            evidence_ids=(EvidenceId("op-rule"),),
            raw_refs=raw_refs,
        ),
    )
    return draft.with_semantic_review(
        SemanticReview.for_draft(
            draft,
            review_id=SemanticReviewId("op-review"),
            reviewer="synthetic-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic fixture review only.",
            authority_scope="synthetic-fixture-only",
        )
    )


def _poly_snapshot(
    *,
    bid: str = "0.10",
    asks: tuple[tuple[str, str], ...] = (("0.30", "1"), ("0.40", "3")),
    asset_id: str = "op-token",
    market_id: str = "op-market",
    raw_ref: RawReference = POLY_RAW,
    fixture_reference: str = "opportunities/cases.json",
) -> PolymarketOrderBookSnapshot:
    payload = {
        "event_type": "book",
        "asset_id": asset_id,
        "market": market_id,
        "bids": [{"price": bid, "size": "10"}],
        "asks": [{"price": price, "size": size} for price, size in asks],
        "timestamp": "1700000000000",
    }
    envelope = RawEnvelope.from_payload(
        venue=Venue.POLYMARKET,
        fixture=FixtureReference(fixture_reference, Venue.POLYMARKET),
        payload=payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://opportunities",
        capture_timestamp=UTC_TIME,
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
    )
    return parse_polymarket_snapshot(envelope)


def _kalshi_snapshot(
    *,
    yes_levels: tuple[tuple[str, str], ...] = (("0.10", "10"),),
    no_levels: tuple[tuple[str, str], ...] = (("0.70", "1"), ("0.75", "3")),
    market: KalshiMarketIdentity | None = None,
    raw_ref: RawReference = KALSHI_RAW,
) -> KalshiOrderBookSnapshot:
    market = market or KalshiMarketIdentity("OP-EVENT-MARKET", "op-market-id")
    return KalshiOrderBookSnapshot(
        venue=Venue.KALSHI,
        market=market,
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
        timestamp=UTC_TIME,
        timestamp_source="venue",
        yes_side=KalshiNativeBookSide.normalized(
            KalshiNativeSideKind.YES,
            tuple(PriceLevel(price, size) for price, size in yes_levels),
        ),
        no_side=KalshiNativeBookSide.normalized(
            KalshiNativeSideKind.NO, tuple(PriceLevel(price, size) for price, size in no_levels)
        ),
        session_id=1,
        sequence=1,
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
        raw_ref=raw_ref,
        raw_refs=(raw_ref,),
        warnings=(),
    )


def _align_polymarket_snapshot(
    snapshot: PolymarketOrderBookSnapshot, binding: PolymarketClaimBinding
) -> PolymarketOrderBookSnapshot:
    order_book = replace(
        snapshot.order_book,
        market=binding.market,
        contract=binding.outcome_token,
        raw_ref=binding.raw_refs[0],
        raw_refs=(binding.raw_refs[0],),
    )
    return replace(snapshot, order_book=order_book)


def _poly_snapshots_for_certificate(
    certificate: Any,
    *,
    asks: tuple[tuple[str, str], ...] = (("0.30", "1"), ("0.40", "3")),
    bid: str = "0.10",
) -> dict[ClaimBindingId, PolymarketOrderBookSnapshot]:
    bindings = certificate.bindings
    return {
        binding.binding_id: _poly_snapshot(
            bid=bid,
            asks=asks,
            asset_id=binding.outcome_token.value,
            market_id=binding.market.value,
            raw_ref=binding.raw_refs[0],
        )
        for binding in bindings
        if isinstance(binding, PolymarketClaimBinding)
    }


def _policy(
    venue: Venue,
    binding: ClaimBindingId,
    *,
    formula: FeeFormulaKind = FeeFormulaKind.ZERO,
    scope: FeeCalculationScope = FeeCalculationScope.PER_DEPTH_SLICE,
    rounding: FeeRoundingScope = FeeRoundingScope.EACH_CALCULATION_COMPONENT,
    params: tuple[tuple[str, DecimalInterval], ...] = (),
    rounding_mode: str = "ROUND_HALF_UP",
    quantum: Decimal = Decimal("0.01"),
) -> FeePolicyAssignment:
    return FeePolicyAssignment(
        binding,
        FeePolicy(
            "fee-policy-v1",
            f"synthetic-policy-{venue.value}-{binding.value}",
            venue,
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            True,
            True,
            FeeRole.TAKER,
            FeeTradeSide.BUY,
            formula,
            params,
            scope,
            rounding,
            rounding_mode,
            "USD",
            quantum,
            (RawReference(f"fee-{venue.value}", venue),),
        ),
    )


def _run(
    relationship: RelationshipType = RelationshipType.COMPLEMENT,
    *,
    kalshi: bool = False,
    quantity: object = Decimal("2"),
    asks: tuple[tuple[str, str], ...] = (("0.30", "1"), ("0.40", "3")),
    snapshots_override: tuple[PolymarketOrderBookSnapshot, ...] | None = None,
    flat_fee: bool = False,
    flat_fee_amount: Decimal = Decimal("0.01"),
    flat_fee_interval: DecimalInterval | None = None,
    rounding_mode: str = "ROUND_HALF_UP",
    rounding_quantum: Decimal = Decimal("0.01"),
    fee_scope: FeeCalculationScope = FeeCalculationScope.PER_DEPTH_SLICE,
    fee_rounding: FeeRoundingScope = FeeRoundingScope.EACH_CALCULATION_COMPONENT,
):
    draft = _draft(relationship, kalshi=kalshi)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots = {
        binding.binding_id: (
            _align_polymarket_snapshot(snapshots_override[index], binding)
            if snapshots_override is not None and isinstance(binding, PolymarketClaimBinding)
            else snapshots_override[index]
            if snapshots_override is not None
            else (
                _kalshi_snapshot(
                    market=binding.market,
                    raw_ref=binding.raw_refs[0],
                )
                if kalshi
                else _poly_snapshot(
                    asks=asks,
                    asset_id=binding.outcome_token.value,
                    market_id=binding.market.value,
                    raw_ref=binding.raw_refs[0],
                )
            )
        )
        for index, binding in enumerate(certificate.bindings)
    }
    policies = tuple(
        _policy(
            Venue.KALSHI if kalshi else Venue.POLYMARKET,
            binding.binding_id,
            formula=FeeFormulaKind.FLAT_PER_CONTRACT if flat_fee else FeeFormulaKind.ZERO,
            scope=fee_scope,
            rounding=fee_rounding,
            params=(
                (
                    "amount",
                    flat_fee_interval
                    if flat_fee_interval is not None
                    else DecimalInterval(flat_fee_amount, flat_fee_amount),
                ),
            )
            if flat_fee
            else (),
            rounding_mode=rounding_mode,
            quantum=rounding_quantum,
        )
        for binding in certificate.bindings
    )
    return evaluate_opportunity(certificate, compiled, snapshots, quantity, policies)


def _run_with_snapshot_mutation(mutator: Callable[[Any], None], *, kalshi: bool = False) -> Any:
    draft = _draft(RelationshipType.COMPLEMENT, kalshi=kalshi)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots: dict[ClaimBindingId, object] = {}
    for binding in certificate.bindings:
        if isinstance(binding, PolymarketClaimBinding):
            snapshot = _poly_snapshot(
                asset_id=binding.outcome_token.value,
                market_id=binding.market.value,
                raw_ref=binding.raw_refs[0],
            )
            snapshot = replace(
                snapshot,
                order_book=replace(
                    snapshot.order_book,
                    bids=BookSide.normalized(
                        BookSideKind.BID,
                        (PriceLevel("0.20", "5"), PriceLevel("0.10", "5")),
                    ),
                ),
            )
        else:
            snapshot = _kalshi_snapshot(
                market=binding.market,
                raw_ref=binding.raw_refs[0],
            )
            snapshot = replace(
                snapshot,
                yes_side=KalshiNativeBookSide.normalized(
                    KalshiNativeSideKind.YES,
                    (PriceLevel("0.20", "5"), PriceLevel("0.10", "5")),
                ),
                no_side=KalshiNativeBookSide.normalized(
                    KalshiNativeSideKind.NO,
                    (PriceLevel("0.75", "5"), PriceLevel("0.70", "5")),
                ),
            )
        snapshots[binding.binding_id] = snapshot
    mutator(snapshots[certificate.bindings[0].binding_id])
    venue = Venue.KALSHI if kalshi else Venue.POLYMARKET
    policies = tuple(_policy(venue, binding.binding_id) for binding in certificate.bindings)
    return evaluate_opportunity(certificate, compiled, snapshots, Decimal("1"), policies)


def _mutate_non_top_level(side: Any, malformation: str) -> None:
    level = side.levels[1]
    if malformation == "non_decimal_price":
        object.__setattr__(level, "price", "0.10")
    elif malformation == "non_decimal_size":
        object.__setattr__(level, "size", "5")
    elif malformation == "non_finite_price":
        object.__setattr__(level, "price", Decimal("NaN"))
    elif malformation == "non_finite_size":
        object.__setattr__(level, "size", Decimal("Infinity"))
    elif malformation == "zero_size":
        object.__setattr__(level, "size", Decimal("0"))
    elif malformation == "negative_size":
        object.__setattr__(level, "size", Decimal("-1"))
    elif malformation == "duplicate_price":
        object.__setattr__(level, "price", side.levels[0].price)
    elif malformation == "reversed_order":
        object.__setattr__(level, "price", side.levels[0].price + Decimal("0.05"))
    elif malformation == "non_price_level":
        object.__setattr__(side, "levels", (side.levels[0], object()))
    elif malformation == "out_of_range_price":
        object.__setattr__(level, "price", Decimal("2"))
    else:  # pragma: no cover - parameter list is closed
        raise AssertionError(malformation)


def _assert_malformed_snapshot_unavailable(result: Any) -> None:
    assert result.status is OpportunityEconomicsStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.evaluation.total_purchase_cost is None
    assert result.evaluation.reasons
    assert result.evaluation.reasons[0].code is OpportunityReasonCode.INVALID_SNAPSHOT
    assert "malformed depth" in result.evaluation.reasons[0].message


def _fixture_document() -> dict[str, Any]:
    path = FIXTURES / "opportunities" / "cases.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == "opportunity-fixtures-v2"
    assert document["synthetic"] is True
    assert document["authoritative"] is False
    assert "non-authoritative" in document["notice"]
    assert document["fixture_artifact"] == "opportunities/cases.json"
    return document


def _fixture_case(case_id: str) -> dict[str, Any]:
    cases = _fixture_document()["cases"]
    matches = [case for case in cases if case["case_id"] == case_id]
    assert len(matches) == 1
    return matches[0]


def _fixture_raw(label: str, venue: Venue) -> RawReference:
    return RawReference(label, venue)


def _fixture_draft(case: dict[str, Any]) -> RelationshipCertificateDraft:
    venue = Venue(case["venue"])
    propositions = tuple(
        Proposition(PropositionId(item["id"]), item["text"]) for item in case["propositions"]
    )
    proposition_by_id = {item.proposition_id.value: item for item in propositions}
    declaration = RelationshipDeclaration(
        RelationshipType(case["relationship"]),
        tuple(item.proposition_id for item in propositions),
    )
    bindings: list[PolymarketClaimBinding | KalshiClaimBinding] = []
    binding_raw_refs: list[RawReference] = []
    for item in case["bindings"]:
        raw_ref = _fixture_raw(item["raw_reference"], venue)
        binding_raw_refs.append(raw_ref)
        if venue is Venue.POLYMARKET:
            bindings.append(
                PolymarketClaimBinding(
                    proposition_id=PropositionId(item["proposition_id"]),
                    binding_id=ClaimBindingId(item["binding_id"]),
                    classification=ClaimClassification.BINARY_UNIT,
                    market=MarketReference(item["market_id"], venue),
                    outcome_token=ContractReference(item["outcome_token_id"], venue),
                    native_outcome_side=item["native_side"],
                    evidence_ids=(EvidenceId(f"{case['case_id']}-rule"),),
                    raw_refs=(raw_ref,),
                )
            )
        else:
            bindings.append(
                KalshiClaimBinding(
                    proposition_id=PropositionId(item["proposition_id"]),
                    binding_id=ClaimBindingId(item["binding_id"]),
                    classification=ClaimClassification.BINARY_UNIT,
                    market=KalshiMarketIdentity(item["market_ticker"], item["market_id"]),
                    native_side=KalshiNativeSideKind(item["native_side"]),
                    evidence_ids=(EvidenceId(f"{case['case_id']}-rule"),),
                    raw_refs=(raw_ref,),
                )
            )
    raw_refs = tuple(binding_raw_refs)
    rule_id = EvidenceId(f"{case['case_id']}-rule")
    evidence = Evidence(
        evidence_id=rule_id,
        kind=EvidenceKind.MARKET_RULE,
        rule_text="Synthetic fixture rule text.",
        locator=f"fixtures/opportunities/cases.json#{case['case_id']}",
        raw_refs=raw_refs,
        synthetic=True,
    )
    binding_by_id = {item.binding_id.value: item for item in bindings}
    states = tuple(
        FeasibleState(
            FeasibleStateId(item["state_id"]),
            TerminalStateKind(item["terminal_kind"]),
            {
                proposition_by_id[proposition_id].proposition_id: value
                for proposition_id, value in item["truth"].items()
            },
            {
                binding_by_id[binding_id].binding_id: Decimal(value)
                for binding_id, value in item["payouts"].items()
            },
            evidence_ids=tuple(EvidenceId(value) for value in item["evidence_ids"]),
            raw_refs=tuple(_fixture_raw(value, venue) for value in item["raw_references"]),
        )
        for item in case["states"]
    )
    candidate = RelationshipCandidate(
        CandidateId(f"fixture-candidate-{case['case_id']}"),
        tuple(item.proposition_id for item in propositions),
        declaration,
        evidence_ids=(rule_id,),
        raw_refs=raw_refs,
    )
    draft = RelationshipCertificateDraft(
        draft_id=DraftId(f"fixture-draft-{case['case_id']}"),
        originating_candidate_id=candidate.candidate_id,
        propositions=propositions,
        bindings=tuple(bindings),
        proposed_relationship=declaration,
        evidence=(evidence,),
        event_scope=case["event_scope"],
        thresholds=(),
        observation_period=None,
        close_time=UTC_TIME,
        resolution_time=UTC_TIME,
        resolution_sources=(rule_id,),
        cancellation_behavior="retained",
        void_behavior="retained",
        refund_behavior="retained",
        payout_structure="binary unit payout",
        edge_cases=(),
        assumptions=("synthetic only",),
        uncertainties=("not production authority",),
        evidence_provenance=raw_refs,
        validation_method="truth-payoff-exhaustive-supplied-v1",
        feasible_states=states,
        completeness=CompletenessDeclaration(
            True,
            "Synthetic supplied state space only.",
            "synthetic-fixture-only",
            evidence_ids=(rule_id,),
            raw_refs=raw_refs,
        ),
    )
    return draft.with_semantic_review(
        SemanticReview.for_draft(
            draft,
            review_id=SemanticReviewId(f"fixture-review-{case['case_id']}"),
            reviewer="synthetic-fixture-reviewer",
            decision=ReviewDecision.APPROVED,
            reviewed_at=UTC_TIME,
            basis="Synthetic fixture review only.",
            authority_scope="synthetic-fixture-only",
        )
    )


def _fixture_snapshots(case: dict[str, Any]) -> dict[ClaimBindingId, object]:
    venue = Venue(case["venue"])
    result: dict[ClaimBindingId, object] = {}
    capture_timestamp = datetime.fromisoformat(case["timestamp"])
    for item in case["snapshots"]:
        raw_reference = item["raw_reference"]
        fixture = FixtureReference(item["fixture_reference"], venue)
        if venue is Venue.POLYMARKET:
            payload = {
                "event_type": "book",
                "asset_id": item["asset_id"],
                "market": item["market_id"],
                "bids": [{"price": price, "size": size} for price, size in item["bids"]],
                "asks": [{"price": price, "size": size} for price, size in item["asks"]],
                "timestamp": item["timestamp_ms"],
                "fixture_raw_reference": raw_reference,
            }
            envelope = RawEnvelope.from_payload(
                venue=venue,
                fixture=fixture,
                payload=payload,
                source_type=SourceType.FIXTURE_WEBSOCKET,
                endpoint_or_channel="fixture://opportunities/cases.json",
                capture_timestamp=capture_timestamp,
                schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
            )
            snapshot = parse_polymarket_snapshot(envelope)
        else:
            payload = {
                "type": "orderbook_snapshot",
                "sid": item["session_id"],
                "seq": item["sequence"],
                "msg": {
                    "market_ticker": item["market_ticker"],
                    "market_id": item["market_id"],
                    "yes_dollars_fp": item["yes_side"],
                    "no_dollars_fp": item["no_side"],
                    "ts": item["timestamp_ms"],
                    "fixture_raw_reference": raw_reference,
                },
            }
            envelope = RawEnvelope.from_payload(
                venue=venue,
                fixture=fixture,
                payload=payload,
                source_type=SourceType.FIXTURE_WEBSOCKET,
                endpoint_or_channel="fixture://opportunities/cases.json",
                capture_timestamp=capture_timestamp,
                schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
            )
            snapshot = parse_kalshi_snapshot(
                envelope, price_convention=KalshiPriceConvention(item["price_convention"])
            )
        result[ClaimBindingId(item["binding_id"])] = snapshot
    return result


def _fixture_policies(case: dict[str, Any]) -> tuple[FeePolicyAssignment, ...]:
    venue = Venue(case["venue"])
    assignments = []
    for item in case["fee_policies"]:
        parameters = tuple(
            (
                parameter["name"],
                DecimalInterval(parameter["lower"], parameter["upper"]),
            )
            for parameter in item["formula_parameters"]
        )
        policy = FeePolicy(
            item["schema_version"],
            item["policy_id"],
            Venue(item["venue"]),
            datetime.fromisoformat(item["effective_start"]),
            datetime.fromisoformat(item["effective_end"]),
            item["start_inclusive"],
            item["end_inclusive"],
            FeeRole(item["role"]),
            FeeTradeSide(item["trade_side"]),
            FeeFormulaKind(item["formula_kind"]),
            parameters,
            FeeCalculationScope(item["calculation_scope"]),
            FeeRoundingScope(item["rounding_scope"]),
            item["rounding_mode"],
            item["currency"],
            Decimal(item["rounding_quantum"]),
            tuple(_fixture_raw(value, venue) for value in item["provenance"]),
        )
        assignments.append(FeePolicyAssignment(ClaimBindingId(item["binding_id"]), policy))
    return tuple(assignments)


def _evaluate_fixture_case(case: dict[str, Any]):
    draft = _fixture_draft(case)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    return evaluate_opportunity(
        certificate,
        constraint,
        _fixture_snapshots(case),
        Decimal(case["quantity"]),
        _fixture_policies(case),
    )


def _assert_fixture_economics(case: dict[str, Any], result: Any) -> None:
    expected = case["expected"]
    assert result.status.value == expected["status"]
    assert (result.candidate is not None) is expected["candidate"]
    if result.candidate is not None:
        assert is_trusted_candidate(result.candidate)
        assert result.candidate.non_actionable is True
    evaluation = result.evaluation
    assert evaluation.quantity == Decimal(case["quantity"])
    assert evaluation.total_purchase_cost == Decimal(expected["total_purchase_cost"])
    assert evaluation.total_fee_interval == DecimalInterval(*expected["total_fee_interval"])
    assert evaluation.aggregate_gross_edge == DecimalInterval(*expected["aggregate_gross_edge"])
    assert evaluation.aggregate_net_edge == DecimalInterval(*expected["aggregate_net_edge"])
    assert len(evaluation.legs) == len(expected["legs"])
    for leg, expected_leg in zip(evaluation.legs, expected["legs"], strict=True):
        assert leg.claim_binding_id.value == expected_leg["binding_id"]
        assert leg.native_claim_side == expected_leg["native_side"]
        assert leg.required_quantity == Decimal(case["quantity"])
        assert leg.observed_ask_capacity == Decimal(expected_leg["observed_ask_capacity"])
        assert leg.total_purchase_cost == Decimal(expected_leg["total_purchase_cost"])
        assert leg.vwap == Decimal(expected_leg["vwap"])
        assert leg.fee_interval == DecimalInterval(*expected_leg["fee_interval"])
        assert tuple(
            {
                "index": item.index,
                "quantity": str(item.quantity),
                "price": str(item.price),
                "cost": str(item.cost),
            }
            for item in leg.depth_slices
        ) == tuple(
            {
                "index": item["index"],
                "quantity": item["quantity"],
                "price": item["price"],
                "cost": item["cost"],
            }
            for item in expected_leg["depth_slices"]
        )
    assert tuple(item.state_id for item in evaluation.state_results) == tuple(
        item["state_id"] for item in expected["state_results"]
    )
    for state, expected_state in zip(
        evaluation.state_results, expected["state_results"], strict=True
    ):
        assert state.gross_payoff == Decimal(expected_state["gross_payoff"])
        assert state.gross_edge == Decimal(expected_state["gross_edge"])
        assert state.net_edge_lower == Decimal(expected_state["net_edge_lower"])
        assert state.net_edge_upper == Decimal(expected_state["net_edge_upper"])


def _hash_seed_output(seed: str) -> dict[str, str]:
    root = FIXTURES.parent
    script = """
import importlib.util
import json
from pathlib import Path
from invariant_engine.opportunities import is_trusted_candidate
from invariant_engine.serialization import stable_json_bytes

path = Path("tests/opportunities/test_opportunities.py").resolve()
spec = importlib.util.spec_from_file_location("opportunity_tests", path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
result = module._evaluate_fixture_case(module._fixture_case("complement-polymarket-direct"))
assert result.candidate is not None and is_trusted_candidate(result.candidate)
print(json.dumps({
    "evaluation_id": result.evaluation.evaluation_id,
    "candidate_id": result.candidate.candidate_id,
    "evaluation": stable_json_bytes(result.evaluation).decode("utf-8"),
    "candidate": stable_json_bytes(result.candidate).decode("utf-8"),
}, sort_keys=True, separators=(",", ":")))
"""
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = seed
    environment["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_opportunity_fixture_schema_is_synthetic_and_complete() -> None:
    document = _fixture_document()
    assert document["schema_version"] == "opportunity-fixtures-v2"
    assert document["synthetic"] is True
    assert document["authoritative"] is False
    assert len(document["cases"]) == 3
    assert tuple(case["relationship"] for case in document["cases"]) == (
        "complement",
        "exhaustive_set",
        "exclusive_and_exhaustive_partition",
    )
    assert all(case["quantity"] for case in document["cases"])
    assert all(case["snapshots"] and case["fee_policies"] for case in document["cases"])
    assert all(
        snapshot["fixture_reference"] == "opportunities/cases.json"
        for case in document["cases"]
        for snapshot in case["snapshots"]
    )
    for path in (FIXTURES / "opportunities").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case_id",
    [
        "complement-polymarket-direct",
        "exhaustive-set-polymarket-direct",
        "partition-kalshi-derived-asks",
    ],
)
def test_fixture_cases_drive_complete_supported_economics(case_id: str) -> None:
    case = _fixture_case(case_id)
    result = _evaluate_fixture_case(case)
    _assert_fixture_economics(case, result)
    assert result.evaluation.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    binding_ids = tuple(item["binding_id"] for item in case["bindings"])
    assert tuple(leg.claim_binding_id.value for leg in result.evaluation.legs) == binding_ids
    if case["venue"] == "polymarket":
        token_ids = tuple(item["outcome_token_id"] for item in case["bindings"])
        assert len(set(token_ids)) == len(token_ids)
        assert tuple(leg.contract.value for leg in result.evaluation.legs) == token_ids
        assert tuple(leg.market.value for leg in result.evaluation.legs) == tuple(
            item["market_id"] for item in case["bindings"]
        )
    else:
        market_ids = tuple(item["market_id"] for item in case["bindings"])
        assert len(set(market_ids)) == len(market_ids)
        assert tuple(leg.market.market_id for leg in result.evaluation.legs) == market_ids
        assert tuple(leg.market.market_ticker for leg in result.evaluation.legs) == tuple(
            item["market_ticker"] for item in case["bindings"]
        )
    assert all(leg.raw_refs for leg in result.evaluation.legs)
    assert result.evaluation.observation_provenance == tuple(
        raw_ref for leg in result.evaluation.legs for raw_ref in leg.raw_refs
    )


def test_fixture_cases_preserve_distinct_identity_and_ordered_provenance() -> None:
    for case in _fixture_document()["cases"]:
        draft = _fixture_draft(case)
        snapshots = _fixture_snapshots(case)
        for binding in draft.bindings:
            snapshot = snapshots[binding.binding_id]
            if isinstance(binding, PolymarketClaimBinding):
                assert snapshot.asset == binding.outcome_token
                assert snapshot.market == binding.market
            else:
                assert snapshot.market == binding.market
        result = _evaluate_fixture_case(case)
        expected = case["expected"]
        assert all(
            leg.raw_refs and len(set(leg.raw_refs)) == len(leg.raw_refs)
            for leg in result.evaluation.legs
        )
        assert result.evaluation.observation_provenance == tuple(
            raw_ref for leg in result.evaluation.legs for raw_ref in leg.raw_refs
        )
        assert tuple(leg.snapshot_schema_version for leg in result.evaluation.legs) == tuple(
            POLYMARKET_DIRECT_SCHEMA_VERSION
            if case["venue"] == "polymarket"
            else KALSHI_ORDERBOOK_SCHEMA_VERSION
            for _ in expected["legs"]
        )
        assert tuple(item["binding_id"] for item in expected["legs"]) == tuple(
            leg.claim_binding_id.value for leg in result.evaluation.legs
        )


def test_opportunity_fixture_is_hash_seed_deterministic_in_fresh_processes() -> None:
    outputs = [_hash_seed_output(seed) for seed in ("1", "2", "random")]
    assert outputs[0] == outputs[1] == outputs[2]
    assert outputs[0]["evaluation_id"].startswith("opportunity-evaluation:")
    assert outputs[0]["candidate_id"].startswith("opportunity-candidate:")
    assert "trust" not in outputs[0]["evaluation"].lower()
    assert "trust" not in outputs[0]["candidate"].lower()


@pytest.mark.parametrize(
    "relationship",
    [
        RelationshipType.COMPLEMENT,
        RelationshipType.EXHAUSTIVE_SET,
        RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
    ],
)
def test_three_supported_underpricing_classes_validate(relationship: RelationshipType) -> None:
    result = _run(relationship)
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    assert is_trusted_candidate(result.candidate)
    assert result.evaluation.aggregate_net_edge is not None
    assert result.evaluation.aggregate_net_edge.lower > 0


def test_direct_polymarket_depth_is_ordered_and_exact() -> None:
    result = _run(quantity=Decimal("2"), asks=(("0.30", "1"), ("0.40", "3")))
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    assert result.evaluation.legs[0].depth_slices == (
        result.evaluation.legs[0].depth_slices[0],
        result.evaluation.legs[0].depth_slices[1],
    )
    assert tuple(item.quantity for item in result.evaluation.legs[0].depth_slices) == (
        Decimal("1"),
        Decimal("1"),
    )
    assert result.evaluation.legs[0].total_purchase_cost == Decimal("0.70")
    assert result.evaluation.legs[0].vwap == Decimal("0.35")
    assert result.evaluation.legs[0].observed_ask_capacity == Decimal("4")


def test_derived_kalshi_depth_is_used_and_native_identity_retained() -> None:
    result = _run(kalshi=True, quantity=Decimal("4"))
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    assert all(leg.venue is Venue.KALSHI for leg in result.evaluation.legs)
    assert all(leg.contract is None for leg in result.evaluation.legs)
    assert result.evaluation.legs[0].depth_slices[0].price == Decimal("0.25")
    assert result.evaluation.legs[0].depth_slices[1].price == Decimal("0.30")
    assert any(warning.code is WarningCode.DERIVED_VALUE for warning in result.evaluation.warnings)


def test_derived_kalshi_no_asks_remain_valid_and_native() -> None:
    draft = _draft(
        RelationshipType.COMPLEMENT,
        kalshi=True,
        kalshi_native_side=KalshiNativeSideKind.NO,
    )
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots = {
        binding.binding_id: _kalshi_snapshot(
            yes_levels=(("0.70", "1"), ("0.75", "3")),
            no_levels=(("0.10", "10"),),
            market=binding.market,
            raw_ref=binding.raw_refs[0],
        )
        for binding in certificate.bindings
        if isinstance(binding, KalshiClaimBinding)
    }
    policies = tuple(_policy(Venue.KALSHI, binding.binding_id) for binding in certificate.bindings)
    result = evaluate_opportunity(certificate, compiled, snapshots, Decimal("4"), policies)
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    assert all(leg.native_claim_side == "no" for leg in result.evaluation.legs)
    assert result.evaluation.legs[0].depth_slices[0].price == Decimal("0.25")
    assert result.evaluation.legs[0].depth_slices[1].price == Decimal("0.30")
    assert any(warning.code is WarningCode.DERIVED_VALUE for warning in result.evaluation.warnings)


def test_insufficient_depth_is_reported_for_each_possible_leg() -> None:
    result = _run(quantity=Decimal("5"), asks=(("0.30", "1"),))
    assert result.status is OpportunityEconomicsStatus.INSUFFICIENT_DEPTH
    assert len(result.evaluation.reasons) == 2
    assert all(
        reason.code is OpportunityReasonCode.INSUFFICIENT_DEPTH
        for reason in result.evaluation.reasons
    )


def test_explicit_incomplete_depth_warning_is_unavailable() -> None:
    snapshot = _poly_snapshot()
    asks = replace(
        snapshot.order_book.asks,
        warnings=(WarningRecord(WarningCode.INCOMPLETE_DEPTH, "synthetic truncated book"),),
    )
    incomplete = replace(snapshot, order_book=replace(snapshot.order_book, asks=asks))
    result = _run(snapshots_override=(incomplete, incomplete))
    assert result.status is OpportunityEconomicsStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.evaluation.total_purchase_cost is None
    assert "incomplete" in result.evaluation.reasons[0].message


def test_mutated_non_top_price_is_unavailable_before_economics() -> None:
    snapshot = _poly_snapshot()
    object.__setattr__(snapshot.order_book.asks.levels[1], "price", Decimal("2"))
    result = _run(snapshots_override=(snapshot, snapshot), quantity=Decimal("2"))
    assert result.status is OpportunityEconomicsStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.evaluation.total_purchase_cost is None
    assert "malformed depth" in result.evaluation.reasons[0].message


@pytest.mark.parametrize("malformation", ["size", "reversed", "duplicate"])
def test_malformed_non_top_depth_is_unavailable(malformation: str) -> None:
    snapshot = _poly_snapshot()
    if malformation == "size":
        object.__setattr__(snapshot.order_book.asks.levels[1], "size", Decimal("-1"))
    elif malformation == "reversed":
        object.__setattr__(snapshot.order_book.asks.levels[0], "price", Decimal("0.40"))
        object.__setattr__(snapshot.order_book.asks.levels[1], "price", Decimal("0.30"))
    else:
        object.__setattr__(snapshot.order_book.asks.levels[1], "price", Decimal("0.30"))
    result = _run(snapshots_override=(snapshot, snapshot), quantity=Decimal("2"))
    assert result.status is OpportunityEconomicsStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.evaluation.total_purchase_cost is None
    assert "malformed depth" in result.evaluation.reasons[0].message


def test_non_top_polymarket_bid_out_of_range_is_unavailable_before_economics() -> None:
    def mutate(snapshot: Any) -> None:
        _mutate_non_top_level(snapshot.order_book.bids, "out_of_range_price")

    _assert_malformed_snapshot_unavailable(_run_with_snapshot_mutation(mutate))


@pytest.mark.parametrize(
    "malformation",
    [
        "non_decimal_price",
        "non_decimal_size",
        "non_finite_price",
        "non_finite_size",
        "zero_size",
        "negative_size",
        "duplicate_price",
        "reversed_order",
        "non_price_level",
    ],
)
def test_malformed_non_top_polymarket_bid_is_unavailable(malformation: str) -> None:
    def mutate(snapshot: Any) -> None:
        _mutate_non_top_level(snapshot.order_book.bids, malformation)

    _assert_malformed_snapshot_unavailable(_run_with_snapshot_mutation(mutate))


def test_polymarket_bid_side_with_wrong_kind_is_unavailable() -> None:
    def mutate(snapshot: Any) -> None:
        object.__setattr__(snapshot.order_book.bids, "kind", BookSideKind.ASK)

    _assert_malformed_snapshot_unavailable(_run_with_snapshot_mutation(mutate))


@pytest.mark.parametrize("native_side", ["yes_side", "no_side"])
@pytest.mark.parametrize(
    "malformation",
    [
        "out_of_range_price",
        "non_decimal_price",
        "non_decimal_size",
        "non_finite_price",
        "non_finite_size",
        "zero_size",
        "negative_size",
        "duplicate_price",
        "reversed_order",
        "non_price_level",
    ],
)
def test_malformed_non_top_kalshi_native_side_is_unavailable(
    native_side: str, malformation: str
) -> None:
    def mutate(snapshot: Any) -> None:
        _mutate_non_top_level(getattr(snapshot, native_side), malformation)

    _assert_malformed_snapshot_unavailable(_run_with_snapshot_mutation(mutate, kalshi=True))


@pytest.mark.parametrize(
    ("native_side", "wrong_kind"),
    [
        ("yes_side", KalshiNativeSideKind.NO),
        ("no_side", KalshiNativeSideKind.YES),
    ],
)
def test_kalshi_native_side_with_wrong_kind_is_unavailable(
    native_side: str, wrong_kind: KalshiNativeSideKind
) -> None:
    def mutate(snapshot: Any) -> None:
        object.__setattr__(getattr(snapshot, native_side), "kind", wrong_kind)

    _assert_malformed_snapshot_unavailable(_run_with_snapshot_mutation(mutate, kalshi=True))


@pytest.mark.parametrize(
    "relationship",
    [
        RelationshipType.IMPLICATION,
        RelationshipType.EQUIVALENCE,
        RelationshipType.SUBSET,
        RelationshipType.SUPERSET,
        RelationshipType.MUTUALLY_EXCLUSIVE_SET,
    ],
)
def test_unsupported_relationship_directions_never_walk_fees(
    relationship: RelationshipType,
) -> None:
    first = _poly_snapshot(bid="0.60", asks=(("0.60", "4"),))
    second = _poly_snapshot(bid="0.20", asks=(("0.20", "4"),))
    if relationship is RelationshipType.SUPERSET:
        first, second = second, first
    if relationship is RelationshipType.MUTUALLY_EXCLUSIVE_SET:
        second = first
    result = _run(relationship, snapshots_override=(first, second))
    assert result.status is OpportunityEconomicsStatus.UNSUPPORTED_TRADE_DIRECTION
    assert result.candidate is None


def test_above_bound_partition_is_unsupported() -> None:
    draft = _draft(RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshot = _poly_snapshot(bid="0.60", asks=(("0.60", "4"),))
    snapshots = {
        binding.binding_id: _align_polymarket_snapshot(snapshot, binding)
        for binding in certificate.bindings
    }
    policies = tuple(
        _policy(Venue.POLYMARKET, binding.binding_id) for binding in certificate.bindings
    )
    result = evaluate_opportunity(certificate, compiled, snapshots, Decimal("1"), policies)
    assert result.status is OpportunityEconomicsStatus.UNSUPPORTED_TRADE_DIRECTION


def test_fresh_reconstruction_rejects_mismatched_constraint_and_ignores_supplied_evaluation() -> (
    None
):
    draft = _draft(RelationshipType.COMPLEMENT)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots = _poly_snapshots_for_certificate(certificate)
    policies = tuple(
        _policy(Venue.POLYMARKET, binding.binding_id) for binding in certificate.bindings
    )
    fresh = evaluate_constraint(
        compiled,
        tuple(
            observe_polymarket(binding, snapshots[binding.binding_id]).observation
            for binding in certificate.bindings
        ),
    ).evaluation
    assert fresh is not None and fresh.status is ConstraintEvaluationStatus.VIOLATED
    mismatched = replace(compiled, bound=Decimal("0"))
    mismatch_result = evaluate_opportunity(
        certificate, mismatched, snapshots, Decimal("1"), policies
    )
    assert mismatch_result.status is OpportunityEconomicsStatus.UNAVAILABLE
    supplied_sat = replace(fresh, status=ConstraintEvaluationStatus.SATISFIED)
    actual = evaluate_opportunity(
        certificate,
        compiled,
        snapshots,
        Decimal("1"),
        policies,
        constraint_evaluation=supplied_sat,
    )
    assert actual.status is OpportunityEconomicsStatus.VALIDATED


def test_no_candidate_for_upstream_non_violation_or_bad_quantity() -> None:
    draft = _draft(RelationshipType.COMPLEMENT)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots = _poly_snapshots_for_certificate(certificate, asks=(("0.60", "4"),))
    policies = tuple(
        _policy(Venue.POLYMARKET, binding.binding_id) for binding in certificate.bindings
    )
    satisfied = evaluate_opportunity(certificate, compiled, snapshots, Decimal("1"), policies)
    assert satisfied.status is OpportunityEconomicsStatus.UNAVAILABLE
    assert satisfied.candidate is None
    invalid = evaluate_opportunity(certificate, compiled, snapshots, 1.0, policies)
    assert invalid.status is OpportunityEconomicsStatus.UNAVAILABLE


def test_fee_bounds_rounding_and_terminal_states_are_retained() -> None:
    draft = _draft(
        RelationshipType.COMPLEMENT,
        terminal_kinds=(TerminalStateKind.NORMAL, TerminalStateKind.CANCELLATION),
    )
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    snapshots = _poly_snapshots_for_certificate(certificate)
    policies = tuple(
        _policy(
            Venue.POLYMARKET,
            binding.binding_id,
            formula=FeeFormulaKind.QUADRATIC_PRICE,
            params=(("rate", DecimalInterval("0.01", "0.02")),),
            scope=FeeCalculationScope.PER_LEG_AGGREGATE,
            rounding=FeeRoundingScope.LEG_TOTAL,
        )
        for binding in certificate.bindings
    )
    result = evaluate_opportunity(certificate, compiled, snapshots, Decimal("2"), policies)
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.evaluation.total_fee_interval is not None
    assert result.evaluation.total_fee_interval.lower < result.evaluation.total_fee_interval.upper
    assert len(result.evaluation.state_results) == len(certificate.feasible_states)
    assert len(result.evaluation.residual_failures) == len(certificate.bindings)
    assert all(
        len(item.states) == len(certificate.feasible_states)
        for item in result.evaluation.residual_failures
    )


def test_non_power_of_ten_quantum_rounds_each_component_to_a_multiple() -> None:
    result = _run(
        quantity=Decimal("1"),
        asks=(("0.30", "1"),),
        flat_fee=True,
        flat_fee_amount=Decimal("0.03"),
        rounding_quantum=Decimal("0.05"),
    )
    assert result.status is OpportunityEconomicsStatus.VALIDATED
    assert result.candidate is not None
    assert result.evaluation.total_fee_interval == DecimalInterval("0.10", "0.10")
    assert result.evaluation.aggregate_net_edge == DecimalInterval("0.30", "0.30")


def test_non_power_of_ten_quantum_can_remove_candidate() -> None:
    result = _run(
        quantity=Decimal("1"),
        asks=(("0.46", "1"),),
        flat_fee=True,
        flat_fee_amount=Decimal("0.03"),
        rounding_quantum=Decimal("0.05"),
    )
    assert result.status is OpportunityEconomicsStatus.NO_NET_EDGE
    assert result.candidate is None
    assert result.evaluation.total_fee_interval == DecimalInterval("0.10", "0.10")
    assert result.evaluation.aggregate_gross_edge == DecimalInterval("0.08", "0.08")
    assert result.evaluation.aggregate_net_edge == DecimalInterval("-0.02", "-0.02")


@pytest.mark.parametrize(
    ("scope", "rounding", "expected"),
    [
        (
            FeeCalculationScope.PER_DEPTH_SLICE,
            FeeRoundingScope.EACH_CALCULATION_COMPONENT,
            Decimal("0.20"),
        ),
        (
            FeeCalculationScope.PER_LEG_AGGREGATE,
            FeeRoundingScope.LEG_TOTAL,
            Decimal("0.10"),
        ),
    ],
)
def test_non_power_of_ten_quantum_respects_fee_scopes(
    scope: FeeCalculationScope,
    rounding: FeeRoundingScope,
    expected: Decimal,
) -> None:
    result = _run(
        quantity=Decimal("2"),
        asks=(("0.30", "1"), ("0.40", "1")),
        flat_fee=True,
        flat_fee_amount=Decimal("0.03"),
        rounding_quantum=Decimal("0.05"),
        fee_scope=scope,
        fee_rounding=rounding,
    )
    assert result.evaluation.total_fee_interval == DecimalInterval(expected, expected)


@pytest.mark.parametrize(
    ("mode", "value", "expected"),
    [
        ("ROUND_HALF_UP", "0.025", "0.05"),
        ("ROUND_HALF_EVEN", "0.025", "0.00"),
        ("ROUND_HALF_EVEN", "0.075", "0.10"),
        ("ROUND_CEILING", "0.051", "0.10"),
        ("ROUND_DOWN", "0.099", "0.05"),
    ],
)
def test_non_power_of_ten_quantum_respects_decimal_rounding_modes(
    mode: str, value: str, expected: str
) -> None:
    policy = _policy(
        Venue.POLYMARKET,
        ClaimBindingId("rounding-binding"),
        rounding_mode=mode,
        quantum=Decimal("0.05"),
    ).policy
    assert _round(policy, Decimal(value)) == Decimal(expected)


def test_non_power_of_ten_quantum_preserves_fee_interval_order() -> None:
    result = _run(
        quantity=Decimal("1"),
        asks=(("0.30", "1"),),
        flat_fee=True,
        flat_fee_interval=DecimalInterval("0.03", "0.08"),
        rounding_quantum=Decimal("0.05"),
    )
    assert result.evaluation.total_fee_interval == DecimalInterval("0.10", "0.20")
    assert result.evaluation.total_fee_interval.lower <= result.evaluation.total_fee_interval.upper


def test_no_net_edge_is_fail_closed_even_when_gross_positive() -> None:
    result = _run(quantity=Decimal("2"), asks=(("0.495", "4"),), flat_fee=True)
    assert result.status is OpportunityEconomicsStatus.NO_NET_EDGE
    assert result.candidate is None
    assert result.evaluation.aggregate_gross_edge is not None
    assert result.evaluation.aggregate_gross_edge.upper > 0


def test_malformed_snapshot_stale_crossed_and_unsynchronized_fail_closed() -> None:
    draft = _draft(RelationshipType.COMPLEMENT)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    compiled = compile_certificate(certificate).constraint
    assert compiled is not None
    good = _poly_snapshot(
        asset_id="op-token-0", market_id="op-market", raw_ref=certificate.bindings[0].raw_refs[0]
    )
    good_second = _poly_snapshot(
        asset_id="op-token-1", market_id="op-market", raw_ref=certificate.bindings[1].raw_refs[0]
    )
    stale = replace(
        good,
        order_book=replace(
            good.order_book,
            warnings=(WarningRecord(WarningCode.STALE_SNAPSHOT, "synthetic stale"),),
        ),
    )
    policies = tuple(
        _policy(Venue.POLYMARKET, binding.binding_id) for binding in certificate.bindings
    )
    stale_result = evaluate_opportunity(
        certificate,
        compiled,
        {
            certificate.bindings[0].binding_id: stale,
            certificate.bindings[1].binding_id: good_second,
        },
        Decimal("1"),
        policies,
    )
    assert stale_result.status is OpportunityEconomicsStatus.UNAVAILABLE
    crossed = replace(
        good,
        order_book=replace(
            good.order_book,
            bids=BookSide.normalized(BookSideKind.BID, (PriceLevel("0.9", "1"),)),
        ),
    )
    crossed_result = evaluate_opportunity(
        certificate,
        compiled,
        {
            certificate.bindings[0].binding_id: crossed,
            certificate.bindings[1].binding_id: replace(
                crossed,
                order_book=replace(
                    crossed.order_book,
                    contract=certificate.bindings[1].outcome_token,
                    raw_ref=certificate.bindings[1].raw_refs[0],
                    raw_refs=(certificate.bindings[1].raw_refs[0],),
                ),
            ),
        },
        Decimal("1"),
        policies,
    )
    assert crossed_result.status is OpportunityEconomicsStatus.UNAVAILABLE
    unsynchronized = replace(
        good, order_book=replace(good.order_book, timestamp=UTC_TIME.replace(second=21))
    )
    unsync_result = evaluate_opportunity(
        certificate,
        compiled,
        {
            certificate.bindings[0].binding_id: good,
            certificate.bindings[1].binding_id: replace(
                unsynchronized,
                order_book=replace(
                    unsynchronized.order_book,
                    contract=certificate.bindings[1].outcome_token,
                    raw_ref=certificate.bindings[1].raw_refs[0],
                    raw_refs=(certificate.bindings[1].raw_refs[0],),
                ),
            ),
        },
        Decimal("1"),
        policies,
    )
    assert unsync_result.status is OpportunityEconomicsStatus.UNAVAILABLE


def test_candidate_mutation_copy_pickle_json_and_serialization_do_not_transfer_trust() -> None:
    result = _run()
    candidate = result.candidate
    assert candidate is not None and is_trusted_candidate(candidate)
    original_id = candidate.candidate_id
    object.__setattr__(candidate, "non_actionable", False)
    assert candidate.candidate_id == original_id
    assert not is_trusted_candidate(candidate)
    object.__setattr__(candidate, "non_actionable", True)
    object.__setattr__(candidate, "candidate_id", "opportunity-candidate:" + "0" * 64)
    assert not is_trusted_candidate(candidate)
    assert not is_trusted_candidate(copy.copy(candidate))
    assert not is_trusted_candidate(copy.deepcopy(candidate))
    assert not is_trusted_candidate(pickle.loads(pickle.dumps(candidate)))
    payload = json.loads(stable_json_bytes(candidate))
    assert "_trusted" not in payload
    serialized = stable_json_bytes(candidate).decode().lower()
    assert "registry" not in serialized
    assert "trust_token" not in serialized


def test_candidate_registry_uses_weak_references() -> None:
    result = _run()
    candidate = result.candidate
    assert candidate is not None
    reference = __import__("weakref").ref(candidate)
    del candidate
    del result
    gc.collect()
    assert reference() is None


def test_opportunity_boundary_has_no_socket_path() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "invariant_engine" / "opportunities"
    assert not any("socket" in path.read_text(encoding="utf-8") for path in source.glob("*.py"))
    assert socket.socket is not None
