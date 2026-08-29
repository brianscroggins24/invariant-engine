"""Adversarial tests for bounded historical strategy validation."""

from __future__ import annotations

import copy
import gc
import importlib.util
import json
import os
import pickle
import socket
import subprocess
import sys
import weakref
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, getcontext, setcontext
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import invariant_engine.opportunities as opportunities_api
from invariant_engine.constraints import compile_certificate
from invariant_engine.diagnostics import (
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    AcceptanceCriterion,
    ChronologicalPartition,
    ComparisonOperator,
    CompleteObservationSlot,
    DenominatorSemantics,
    Eligibility,
    EligibilityRule,
    EligibilityRuleKind,
    EvidenceMinimum,
    ExplicitUnavailableSlot,
    GapTreatment,
    MetricAvailability,
    MetricName,
    MetricReference,
    PartitionPurpose,
    ScheduledObservation,
    StrategyValidationSpecification,
    StrategyValidationStatus,
    SuccessfulHistoricalValidationRecord,
    UnavailabilityCode,
    UnavailabilityReason,
    ValidationReasonCode,
    evaluate_strategy_validation,
    is_trusted_historical_validation_record,
)
from invariant_engine.diagnostics.models import _TRUSTED_HISTORICAL_RECORDS
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.opportunities import (
    DecimalInterval,
    FeeFormulaKind,
    OpportunityEconomicsResult,
    OpportunityEconomicsStatus,
    OpportunityReason,
    OpportunityReasonCode,
)
from invariant_engine.relationships import RelationshipType, validate_draft
from invariant_engine.serialization import stable_json_bytes

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "diagnostics" / "strategy_cases.json"
START = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
STRATIFICATION_KEYS = (
    "venue",
    "relationship",
    "currency",
    "fee_regime",
    "sampling_window",
    "strategy_version",
    "time_interval",
)
ECONOMICS_DERIVED_METRICS = (
    MetricName.OBSERVED_DEPTH_DIAGNOSTICS,
    MetricName.PURCHASE_COST,
    MetricName.FEE_INTERVAL,
    MetricName.GROSS_EDGE_INTERVAL,
    MetricName.NET_EDGE_INTERVAL,
    MetricName.RESIDUAL_SINGLE_LEG_FAILURE_RANGES,
)


def _opportunity_helpers() -> ModuleType:
    path = ROOT / "tests" / "opportunities" / "test_opportunities.py"
    spec = importlib.util.spec_from_file_location("accepted_opportunity_test_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OPPORTUNITY_HELPERS = _opportunity_helpers()


def _complete_slot(
    observation_id: str,
    timestamp: datetime,
    *,
    relationship: RelationshipType = RelationshipType.COMPLEMENT,
    venue: Venue = Venue.POLYMARKET,
    mode: str = "validated",
    quantity: Decimal = Decimal("1"),
    currency: str = "USD",
) -> CompleteObservationSlot:
    kalshi = venue is Venue.KALSHI
    draft = OPPORTUNITY_HELPERS._draft(relationship, kalshi=kalshi)
    certificate = validate_draft(draft).certificate
    assert certificate is not None
    constraint = compile_certificate(certificate).constraint
    assert constraint is not None
    snapshots: list[tuple[Any, object]] = []
    for index, binding in enumerate(certificate.bindings):
        if kalshi:
            snapshot = OPPORTUNITY_HELPERS._kalshi_snapshot(
                market=binding.market,
                raw_ref=binding.raw_refs[0],
            )
            snapshot = replace(snapshot, timestamp=timestamp, sequence=index + 1)
        else:
            if mode == "no_net_edge":
                bid, asks = "0.10", (("0.49", "10"),)
            elif mode == "insufficient_depth":
                bid, asks = "0.10", (("0.30", "0.5"),)
            elif mode == "unavailable":
                bid, asks = "0.10", (("0.60", "10"),)
            elif mode == "unsupported":
                bid, asks = (
                    ("0.70", (("0.80", "10"),)) if index == 0 else ("0.10", (("0.20", "10"),))
                )
            else:
                price = Decimal("0.30") + Decimal(index) / Decimal("100")
                bid, asks = "0.10", ((str(price), "10"),)
            snapshot = OPPORTUNITY_HELPERS._poly_snapshot(
                bid=bid,
                asks=asks,
                asset_id=binding.outcome_token.value,
                market_id=binding.market.value,
                raw_ref=binding.raw_refs[0],
                fixture_reference="diagnostics/strategy_cases.json",
            )
            snapshot = replace(
                snapshot, order_book=replace(snapshot.order_book, timestamp=timestamp)
            )
        snapshots.append((binding.binding_id, snapshot))
    policies = []
    for binding in certificate.bindings:
        assignment = OPPORTUNITY_HELPERS._policy(
            venue,
            binding.binding_id,
            formula=(
                FeeFormulaKind.FLAT_PER_CONTRACT if mode == "no_net_edge" else FeeFormulaKind.ZERO
            ),
            params=(("amount", DecimalInterval(Decimal("0.02"), Decimal("0.02"))),)
            if mode == "no_net_edge"
            else (),
        )
        if currency != "USD":
            assignment = replace(
                assignment,
                policy=replace(assignment.policy, currency=currency),
            )
        policies.append(assignment)
    return CompleteObservationSlot(
        observation_id,
        timestamp,
        certificate,
        constraint,
        tuple(snapshots),
        quantity,
        tuple(policies),
        (RawReference(f"diagnostics-{observation_id}", venue),),
    )


def _scheduled(
    slot: CompleteObservationSlot | ExplicitUnavailableSlot,
    *,
    relationship: RelationshipType = RelationshipType.COMPLEMENT,
    venue: Venue = Venue.POLYMARKET,
    currency: str = "USD",
    fee_regime: str = "synthetic-zero-v1",
    grouping: str = "group-a",
    partition_id: str | None = None,
    eligibility: Eligibility = Eligibility.INCLUDED,
) -> ScheduledObservation:
    return ScheduledObservation(
        slot.observation_id,
        slot.timestamp,
        relationship,
        slot.quantity if isinstance(slot, CompleteObservationSlot) else Decimal("1"),
        grouping,
        (
            ("venue", venue.value),
            ("relationship", relationship.value),
            ("currency", currency),
            ("fee_regime", fee_regime),
            ("sampling_window", "explicit-one-minute-v1"),
            ("strategy_version", "synthetic-v1"),
            ("time_interval", slot.timestamp.isoformat()),
        ),
        eligibility,
        ("include-fixed-schedule",) if eligibility is Eligibility.INCLUDED else ("exclude-fixed",),
        partition_id,
    )


def _specification(
    schedule: tuple[ScheduledObservation, ...],
    *,
    required_metrics: tuple[MetricReference, ...] | None = None,
    minimums: tuple[EvidenceMinimum, ...] | None = None,
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
    partitions: tuple[ChronologicalPartition, ...] = (),
    precision: int = 12,
) -> StrategyValidationSpecification:
    scheduled_count = MetricReference(MetricName.SCHEDULED_COUNT, None, None, ())
    frequency = MetricReference(MetricName.VALIDATED_OPPORTUNITY_FREQUENCY, None, None, ())
    return StrategyValidationSpecification(
        STRATEGY_VALIDATION_SCHEMA_VERSION,
        "synthetic-fixed-strategy",
        "synthetic-v1",
        schedule[0].timestamp,
        schedule[-1].timestamp,
        True,
        True,
        tuple(dict.fromkeys(item.relationship_class for item in schedule)),
        schedule,
        "Every listed synthetic timestamp is one complete scheduled observation; no gaps inferred.",
        "relationship-group",
        "Persistence is computed only within each exact grouping identity subsequence.",
        STRATIFICATION_KEYS,
        (
            EligibilityRule(
                "include-fixed-schedule",
                EligibilityRuleKind.INCLUSION,
                "Caller fixed the slot before historical evaluation.",
            ),
        ),
        (
            EligibilityRule(
                "exclude-fixed",
                EligibilityRuleKind.EXCLUSION,
                "Caller explicitly excluded the slot before historical evaluation.",
            ),
        ),
        DenominatorSemantics.ALL_SCHEDULED_OBSERVATIONS,
        GapTreatment.RETAIN_AS_UNAVAILABLE_AND_BREAK_PERSISTENCE,
        partitions,
        required_metrics if required_metrics is not None else (scheduled_count, frequency),
        minimums
        if minimums is not None
        else (EvidenceMinimum("minimum-schedule", scheduled_count, len(schedule)),),
        criteria
        if criteria is not None
        else (
            AcceptanceCriterion(
                "nonnegative-frequency",
                frequency,
                ComparisonOperator.GREATER_THAN_OR_EQUAL,
                Decimal("0"),
            ),
        ),
        precision,
        "ROUND_HALF_EVEN",
        (RawReference("diagnostics-specification", Venue.POLYMARKET),),
    )


def _unavailable_slot(observation_id: str, timestamp: datetime) -> ExplicitUnavailableSlot:
    return ExplicitUnavailableSlot(
        observation_id,
        timestamp,
        UnavailabilityReason(
            UnavailabilityCode.EXPLICIT_SCHEDULE_GAP,
            "Synthetic fixture explicitly records an unavailable scheduled observation.",
        ),
        (RawReference(f"diagnostics-gap-{observation_id}", Venue.POLYMARKET),),
    )


def _validated_outcome() -> Any:
    slots = tuple(
        _complete_slot(f"observation-{index}", START + timedelta(minutes=index))
        for index in range(3)
    )
    schedule = tuple(_scheduled(item) for item in slots)
    return evaluate_strategy_validation(_specification(schedule), slots)


def test_fixture_is_strict_synthetic_complete_and_non_authoritative() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert document["schema_version"] == "diagnostics-fixtures-v1"
    assert document["synthetic"] is True
    assert document["authoritative"] is False
    assert document["production_configuration"] is False
    assert document["trading_recommendation"] is False
    assert document["future_profitability_evidence"] is False
    assert document["coverage"]["relationship_classes"] == [
        "complement",
        "exhaustive_set",
        "exclusive_and_exhaustive_partition",
    ]
    assert set(document["coverage"]["milestone_3_statuses"]) == {
        item.value for item in OpportunityEconomicsStatus
    }
    assert len(document["coverage"]["unsupported_metrics"]) == 11
    assert json.loads(json.dumps(document, sort_keys=True)) == document


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("required_metrics", "required metrics must be non-empty"),
        ("minimums", "evidence minimums must be non-empty"),
        ("criteria", "acceptance criteria must be non-empty"),
    ],
)
def test_each_empty_validation_policy_collection_is_rejected(field: str, message: str) -> None:
    gap = _unavailable_slot("only-gap", START)
    arguments: dict[str, object] = {field: ()}
    with pytest.raises(DomainError, match=message):
        _specification((_scheduled(gap),), **arguments)


def test_entirely_empty_validation_policy_cannot_validate_or_issue_trust() -> None:
    gap = _unavailable_slot("only-gap", START)
    with pytest.raises(DomainError):
        _specification(
            (_scheduled(gap),),
            required_metrics=(),
            minimums=(),
            criteria=(),
        )


@pytest.mark.parametrize(
    "field",
    ["required_metrics", "evidence_minimums", "acceptance_criteria"],
)
def test_post_construction_empty_policy_mutation_fails_closed(field: str) -> None:
    gap = _unavailable_slot("only-gap", START)
    specification = _specification((_scheduled(gap),))
    object.__setattr__(specification, field, ())
    outcome = evaluate_strategy_validation(specification, (gap,))
    assert outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert outcome.result.reasons[0].code is ValidationReasonCode.INVALID_SPECIFICATION
    assert outcome.historical_record is None
    assert outcome.record is None


def test_valid_explicit_policy_retains_deterministic_result_and_trust_behavior() -> None:
    slot = _complete_slot("explicit-policy", START)
    specification = _specification((_scheduled(slot),))
    first = evaluate_strategy_validation(specification, (slot,))
    second = evaluate_strategy_validation(specification, (slot,))
    assert first.status is second.status is StrategyValidationStatus.VALIDATED
    assert first.result.validation_id == second.result.validation_id
    assert first.result.dataset_id == second.result.dataset_id
    assert stable_json_bytes(first.result) == stable_json_bytes(second.result)
    assert first.record is not None and second.record is not None
    assert first.record.record_id == second.record.record_id
    assert is_trusted_historical_validation_record(first.record)
    assert is_trusted_historical_validation_record(second.record)


@pytest.mark.parametrize(
    ("relationship", "venue"),
    [
        (RelationshipType.COMPLEMENT, Venue.POLYMARKET),
        (RelationshipType.EXHAUSTIVE_SET, Venue.POLYMARKET),
        (RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION, Venue.KALSHI),
    ],
)
def test_all_supported_buy_only_classes_and_venues_rerun_milestone_3(
    relationship: RelationshipType, venue: Venue
) -> None:
    slot = _complete_slot("supported", START, relationship=relationship, venue=venue)
    scheduled = _scheduled(slot, relationship=relationship, venue=venue)
    outcome = evaluate_strategy_validation(_specification((scheduled,)), (slot,))
    assert outcome.status is StrategyValidationStatus.VALIDATED
    record = outcome.result.observation_records[0]
    assert record.economics_result is not None
    assert record.economics_result.status is OpportunityEconomicsStatus.VALIDATED
    assert record.economics_result.evaluation.certificate_material is slot.certificate
    assert record.economics_result.evaluation.fresh_constraint_evaluation_material is not None


def test_every_complete_slot_calls_public_milestone_3_evaluator(monkeypatch) -> None:
    slots = tuple(
        _complete_slot(f"spy-{index}", START + timedelta(minutes=index)) for index in range(3)
    )
    specification = _specification(tuple(_scheduled(item) for item in slots))
    calls: list[str] = []
    accepted = opportunities_api.evaluate_opportunity

    def spy(
        certificate: object,
        constraint: object,
        snapshots: object,
        quantity: object,
        policies: object,
    ):
        calls.append(str(getattr(certificate, "certificate_id", "missing")))
        return accepted(certificate, constraint, snapshots, quantity, policies)

    monkeypatch.setattr(opportunities_api, "evaluate_opportunity", spy)
    outcome = evaluate_strategy_validation(specification, slots)
    assert outcome.status is StrategyValidationStatus.VALIDATED
    assert len(calls) == len(slots) == 3
    assert all(item.economics_result is not None for item in outcome.result.observation_records)


def test_supplied_later_artifacts_are_never_authority() -> None:
    slot = _complete_slot("authority", START)
    specification = _specification((_scheduled(slot),))
    expected = evaluate_strategy_validation(specification, (slot,))
    actual = evaluate_strategy_validation(
        specification,
        (slot,),
        opportunity_evaluations=(object(),),
        opportunity_results=(object(),),
        opportunity_candidates=(object(),),
        prior_reports=(expected.result,),
    )
    assert stable_json_bytes(actual.result) == stable_json_bytes(expected.result)
    assert (
        evaluate_strategy_validation(specification, (object(),)).status
        is StrategyValidationStatus.UNAVAILABLE
    )


def test_mixed_status_schedule_counts_rates_and_explicit_gap_denominator() -> None:
    slots = (
        _complete_slot("validated", START),
        _complete_slot("no-edge", START + timedelta(minutes=1), mode="no_net_edge"),
        _complete_slot(
            "depth",
            START + timedelta(minutes=2),
            mode="insufficient_depth",
            quantity=Decimal("2"),
        ),
        _complete_slot(
            "direction",
            START + timedelta(minutes=3),
            relationship=RelationshipType.IMPLICATION,
            mode="unsupported",
        ),
        _complete_slot("m3-unavailable", START + timedelta(minutes=4), mode="unavailable"),
        _unavailable_slot("explicit-gap", START + timedelta(minutes=5)),
    )
    schedule = tuple(
        _scheduled(
            item,
            relationship=(
                RelationshipType.IMPLICATION
                if item.observation_id == "direction"
                else RelationshipType.COMPLEMENT
            ),
        )
        for item in slots
    )
    outcome = evaluate_strategy_validation(_specification(schedule), slots)
    assert outcome.status is StrategyValidationStatus.VALIDATED
    assert outcome.result.scheduled_count == 6
    assert outcome.result.validated_opportunity_frequency.numerator == 1
    assert outcome.result.validated_opportunity_frequency.denominator == 6
    counts = {item.status: item.count for item in outcome.result.status_metrics}
    assert counts == {
        OpportunityEconomicsStatus.VALIDATED: 1,
        OpportunityEconomicsStatus.NO_NET_EDGE: 1,
        OpportunityEconomicsStatus.INSUFFICIENT_DEPTH: 1,
        OpportunityEconomicsStatus.UNSUPPORTED_TRADE_DIRECTION: 1,
        OpportunityEconomicsStatus.UNAVAILABLE: 2,
    }
    assert outcome.result.persistence_runs[0].observation_ids == ("validated",)


def test_every_nonvalidated_milestone_3_status_and_gap_breaks_persistence() -> None:
    slots = (
        _complete_slot("v1", START),
        _complete_slot("no-edge", START + timedelta(minutes=1), mode="no_net_edge"),
        _complete_slot("v2", START + timedelta(minutes=2)),
        _complete_slot(
            "depth",
            START + timedelta(minutes=3),
            mode="insufficient_depth",
            quantity=Decimal("2"),
        ),
        _complete_slot("v3", START + timedelta(minutes=4)),
        _complete_slot(
            "direction",
            START + timedelta(minutes=5),
            relationship=RelationshipType.IMPLICATION,
            mode="unsupported",
        ),
        _complete_slot("v4", START + timedelta(minutes=6)),
        _complete_slot("m3-unavailable", START + timedelta(minutes=7), mode="unavailable"),
        _complete_slot("v5", START + timedelta(minutes=8)),
        _unavailable_slot("gap", START + timedelta(minutes=9)),
        _complete_slot("v6", START + timedelta(minutes=10)),
    )
    schedule = tuple(
        _scheduled(
            item,
            relationship=(
                RelationshipType.IMPLICATION
                if item.observation_id == "direction"
                else RelationshipType.COMPLEMENT
            ),
        )
        for item in slots
    )
    runs = evaluate_strategy_validation(_specification(schedule), slots).result.persistence_runs
    assert tuple(item.observation_ids for item in runs) == tuple(
        (f"v{index}",) for index in range(1, 7)
    )


def test_repeating_ratio_local_context_and_hostile_global_context_are_stable() -> None:
    slots = (
        _complete_slot("one", START),
        _unavailable_slot("two", START + timedelta(minutes=1)),
        _unavailable_slot("three", START + timedelta(minutes=2)),
    )
    schedule = tuple(_scheduled(item) for item in slots)
    reference = MetricReference(MetricName.VALIDATED_OPPORTUNITY_FREQUENCY, None, None, ())
    specification = _specification(
        schedule,
        required_metrics=(reference,),
        criteria=(
            AcceptanceCriterion(
                "one-third-boundary", reference, ComparisonOperator.EQUAL, Decimal("0.333333333333")
            ),
        ),
    )
    original = getcontext().copy()
    first = evaluate_strategy_validation(specification, slots)
    try:
        hostile = getcontext()
        hostile.prec = 2
        hostile.rounding = "ROUND_UP"
        second = evaluate_strategy_validation(specification, slots)
    finally:
        setcontext(original)
    assert first.status is StrategyValidationStatus.VALIDATED
    assert first.result.validated_opportunity_frequency.decimal == Decimal("0.333333333333")
    assert stable_json_bytes(first.result) == stable_json_bytes(second.result)
    assert first.result.validation_id == second.result.validation_id


def test_persistence_respects_groups_boundaries_and_every_break_status() -> None:
    slots = (
        _complete_slot("a1", START),
        _complete_slot("b1", START + timedelta(minutes=1)),
        _complete_slot("a2", START + timedelta(minutes=2)),
        _complete_slot("a-break", START + timedelta(minutes=3), mode="no_net_edge"),
        _complete_slot("a3", START + timedelta(minutes=4)),
        _unavailable_slot("a-gap", START + timedelta(minutes=5)),
        _complete_slot("a4", START + timedelta(minutes=6)),
    )
    schedule = tuple(
        _scheduled(item, grouping="group-b" if item.observation_id == "b1" else "group-a")
        for item in slots
    )
    runs = evaluate_strategy_validation(_specification(schedule), slots).result.persistence_runs
    assert tuple((item.grouping_identity, item.observation_ids) for item in runs) == (
        ("group-a", ("a1", "a2")),
        ("group-a", ("a3",)),
        ("group-a", ("a4",)),
        ("group-b", ("b1",)),
    )
    first = runs[0]
    assert first.start_timestamp == START
    assert first.end_timestamp == START + timedelta(minutes=2)
    assert first.observation_count == 2
    assert first.observed_duration == Decimal("120")
    assert runs[1].observed_duration == Decimal("0")


@pytest.mark.parametrize("mutation", ["omit", "insert", "reorder", "duplicate"])
def test_schedule_shape_attacks_fail_closed(mutation: str) -> None:
    slots = (
        _complete_slot("first", START),
        _complete_slot("second", START + timedelta(minutes=1)),
    )
    specification = _specification(tuple(_scheduled(item) for item in slots))
    attacked: tuple[object, ...]
    if mutation == "omit":
        attacked = slots[:1]
    elif mutation == "insert":
        attacked = (*slots, _unavailable_slot("extra", START + timedelta(minutes=2)))
    elif mutation == "reorder":
        attacked = tuple(reversed(slots))
    else:
        attacked = (slots[0], replace(slots[0], observation_id="second"))
    assert (
        evaluate_strategy_validation(specification, attacked).status
        is StrategyValidationStatus.UNAVAILABLE
    )


def test_duplicate_runtime_and_specification_observation_ids_fail_closed() -> None:
    first = _complete_slot("first", START)
    second = _complete_slot("second", START + timedelta(minutes=1))
    specification = _specification((_scheduled(first), _scheduled(second)))
    duplicate_runtime = (first, replace(second, observation_id="first"))
    result = evaluate_strategy_validation(specification, duplicate_runtime)
    assert result.status is StrategyValidationStatus.UNAVAILABLE
    assert result.result.reasons[0].code is ValidationReasonCode.DUPLICATE_OBSERVATION_ID
    with pytest.raises(DomainError, match="IDs must be unique"):
        _specification((_scheduled(first), replace(_scheduled(second), observation_id="first")))


def test_duplicate_material_and_cross_partition_reuse_fail_closed() -> None:
    first = _complete_slot("first", START)
    second = replace(first, observation_id="second")
    specification = _specification((_scheduled(first), _scheduled(second)))
    duplicate = evaluate_strategy_validation(specification, (first, second))
    assert duplicate.status is StrategyValidationStatus.UNAVAILABLE
    assert duplicate.result.reasons[0].code is ValidationReasonCode.DUPLICATE_MATERIAL

    second_time = START + timedelta(minutes=1)
    second = replace(first, observation_id="second", timestamp=second_time)
    schedule = (
        _scheduled(first, partition_id="validation"),
        _scheduled(second, partition_id="test"),
    )
    partitions = (
        ChronologicalPartition(
            "validation",
            PartitionPurpose.VALIDATION,
            START,
            second_time,
            True,
            False,
            ("first",),
            (RawReference("partition-validation", Venue.POLYMARKET),),
        ),
        ChronologicalPartition(
            "test",
            PartitionPurpose.TEST,
            second_time,
            second_time,
            True,
            True,
            ("second",),
            (RawReference("partition-test", Venue.POLYMARKET),),
        ),
    )
    reused = evaluate_strategy_validation(
        _specification(schedule, partitions=partitions), (first, second)
    )
    assert reused.status is StrategyValidationStatus.UNAVAILABLE
    assert reused.result.reasons[0].code is ValidationReasonCode.CROSS_PARTITION_MATERIAL_REUSE


def test_invalid_overlapping_nonchronological_and_leaking_partitions_reject() -> None:
    slots = (
        _complete_slot("first", START),
        _complete_slot("second", START + timedelta(minutes=1)),
    )
    schedule = (
        _scheduled(slots[0], partition_id="one"),
        _scheduled(slots[1], partition_id="two"),
    )
    provenance = (RawReference("partition", Venue.POLYMARKET),)
    overlapping = (
        ChronologicalPartition(
            "one",
            PartitionPurpose.VALIDATION,
            START,
            START + timedelta(minutes=1),
            True,
            True,
            ("first",),
            provenance,
        ),
        ChronologicalPartition(
            "two",
            PartitionPurpose.TEST,
            START + timedelta(minutes=1),
            START + timedelta(minutes=2),
            True,
            True,
            ("second",),
            provenance,
        ),
    )
    with pytest.raises(DomainError, match="overlap"):
        _specification(schedule, partitions=overlapping)
    leaking = (
        replace(overlapping[0], end=START, end_inclusive=True),
        replace(overlapping[1], start=START + timedelta(minutes=2)),
    )
    with pytest.raises(DomainError, match="temporal leakage"):
        _specification(schedule, partitions=leaking)
    with pytest.raises(DomainError, match="chronological"):
        _specification(schedule, partitions=tuple(reversed(overlapping)))


def test_quantity_relationship_timestamp_and_mutated_nested_material_fail_closed() -> None:
    slot = _complete_slot("probe", START)
    scheduled = _scheduled(slot)
    specification = _specification((scheduled,))
    wrong_quantity = replace(slot, quantity=Decimal("2"))
    assert (
        evaluate_strategy_validation(specification, (wrong_quantity,)).status
        is StrategyValidationStatus.UNAVAILABLE
    )
    wrong_relationship = replace(scheduled, relationship_class=RelationshipType.EXHAUSTIVE_SET)
    relationship_spec = _specification((wrong_relationship,))
    assert (
        evaluate_strategy_validation(relationship_spec, (slot,)).status
        is StrategyValidationStatus.UNAVAILABLE
    )
    shifted = replace(slot, timestamp=START + timedelta(seconds=1))
    shifted_spec = _specification((replace(scheduled, timestamp=shifted.timestamp),))
    assert (
        evaluate_strategy_validation(shifted_spec, (shifted,)).result.reasons[0].code
        is ValidationReasonCode.TEMPORAL_LEAKAGE
    )

    mutated = _complete_slot("mutated", START)
    snapshot = mutated.snapshots[0][1]
    object.__setattr__(snapshot.order_book.asks.levels[0], "size", "not-decimal")
    result = evaluate_strategy_validation(_specification((_scheduled(mutated),)), (mutated,))
    assert result.status is StrategyValidationStatus.UNAVAILABLE
    assert result.result.reasons[0].code is ValidationReasonCode.UNTRUSTED_UPSTREAM


def test_copy_deepcopy_pickle_json_and_subclass_upstream_attacks_fail_closed() -> None:
    slot = _complete_slot("trust", START)
    specification = _specification((_scheduled(slot),))
    for constraint in (
        copy.copy(slot.constraint),
        copy.deepcopy(slot.constraint),
        pickle.loads(pickle.dumps(slot.constraint)),
    ):
        attacked = replace(slot, constraint=constraint)
        assert (
            evaluate_strategy_validation(specification, (attacked,)).status
            is StrategyValidationStatus.UNAVAILABLE
        )
    reconstructed = json.loads(stable_json_bytes(slot.constraint))
    assert (
        evaluate_strategy_validation(specification, (reconstructed,)).status
        is StrategyValidationStatus.UNAVAILABLE
    )

    class SlotSubclass(CompleteObservationSlot):
        pass

    subclass = object.__new__(SlotSubclass)
    for name in (
        "observation_id",
        "timestamp",
        "certificate",
        "constraint",
        "snapshots",
        "quantity",
        "fee_policies",
        "provenance",
    ):
        object.__setattr__(subclass, name, getattr(slot, name))
    assert (
        evaluate_strategy_validation(specification, (subclass,)).status
        is StrategyValidationStatus.UNAVAILABLE
    )


def test_strata_preserve_venue_relationship_currency_fee_partition_and_time() -> None:
    first = _complete_slot("poly", START)
    second = _complete_slot(
        "kalshi",
        START + timedelta(minutes=1),
        relationship=RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
        venue=Venue.KALSHI,
        currency="USDC",
    )
    schedule = (
        _scheduled(first, partition_id="validation"),
        _scheduled(
            second,
            relationship=RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
            venue=Venue.KALSHI,
            currency="USDC",
            fee_regime="synthetic-flat-v1",
            partition_id="test",
        ),
    )
    partitions = (
        ChronologicalPartition(
            "validation",
            PartitionPurpose.VALIDATION,
            START,
            second.timestamp,
            True,
            False,
            ("poly",),
            (RawReference("p1", Venue.POLYMARKET),),
        ),
        ChronologicalPartition(
            "test",
            PartitionPurpose.TEST,
            second.timestamp,
            second.timestamp,
            True,
            True,
            ("kalshi",),
            (RawReference("p2", Venue.KALSHI),),
        ),
    )
    result = evaluate_strategy_validation(
        _specification(schedule, partitions=partitions), (first, second)
    ).result
    full_scopes = {
        item.scope for item in result.strata if len(item.scope) == len(STRATIFICATION_KEYS)
    }
    assert schedule[0].strata in full_scopes
    assert schedule[1].strata in full_scopes
    assert result.observation_records[0].economics_result.evaluation.currency == "USD"
    assert result.observation_records[1].economics_result.evaluation.currency == "USDC"
    assert all(item.economics_result is not None for item in result.observation_records)


@pytest.mark.parametrize(
    ("operator", "threshold", "expected"),
    [
        (ComparisonOperator.LESS_THAN, "1", False),
        (ComparisonOperator.LESS_THAN_OR_EQUAL, "1", True),
        (ComparisonOperator.EQUAL, "1", True),
        (ComparisonOperator.GREATER_THAN_OR_EQUAL, "1", True),
        (ComparisonOperator.GREATER_THAN, "1", False),
    ],
)
def test_exact_criterion_comparison_boundaries(
    operator: ComparisonOperator, threshold: str, expected: bool
) -> None:
    slot = _complete_slot("boundary", START)
    frequency = MetricReference(MetricName.VALIDATED_OPPORTUNITY_FREQUENCY, None, None, ())
    specification = _specification(
        (_scheduled(slot),),
        required_metrics=(frequency,),
        criteria=(AcceptanceCriterion("boundary", frequency, operator, Decimal(threshold)),),
    )
    status = evaluate_strategy_validation(specification, (slot,)).status
    assert (status is StrategyValidationStatus.VALIDATED) is expected


def test_status_precedence_conflicts_are_fail_closed() -> None:
    slot = _complete_slot("precedence", START)
    unsupported = MetricReference(MetricName.LATENCY, None, None, ())
    scheduled_count = MetricReference(MetricName.SCHEDULED_COUNT, None, None, ())
    specification = _specification(
        (_scheduled(slot),),
        required_metrics=(unsupported, scheduled_count),
        minimums=(EvidenceMinimum("impossible", scheduled_count, 2),),
        criteria=(
            AcceptanceCriterion("unsupported", unsupported, ComparisonOperator.EQUAL, Decimal("0")),
        ),
    )
    result = evaluate_strategy_validation(specification, (slot,))
    assert result.status is StrategyValidationStatus.UNAVAILABLE
    assert result.result.reasons[0].code is ValidationReasonCode.UNSUPPORTED_REQUIRED_METRIC
    assert all(item.numeric_value is None for item in result.result.unsupported_metrics)

    evidence_only = _specification(
        (_scheduled(slot),),
        required_metrics=(scheduled_count,),
        minimums=(EvidenceMinimum("impossible", scheduled_count, 2),),
        criteria=(
            AcceptanceCriterion(
                "also-fails", scheduled_count, ComparisonOperator.GREATER_THAN, Decimal("5")
            ),
        ),
    )
    assert (
        evaluate_strategy_validation(evidence_only, (slot,)).status
        is StrategyValidationStatus.INSUFFICIENT_EVIDENCE
    )
    assert (
        evaluate_strategy_validation(specification, ()).result.reasons[0].code
        is ValidationReasonCode.SCHEDULE_MISMATCH
    )


def test_supported_observation_diagnostics_are_explicit_without_financial_pooling() -> None:
    slot = _complete_slot("financial", START)
    references = tuple(
        MetricReference(metric, None, None, ())
        for metric in (
            MetricName.REQUESTED_QUANTITY,
            MetricName.OBSERVED_DEPTH_DIAGNOSTICS,
            MetricName.PURCHASE_COST,
            MetricName.FEE_INTERVAL,
            MetricName.GROSS_EDGE_INTERVAL,
            MetricName.NET_EDGE_INTERVAL,
            MetricName.RESIDUAL_SINGLE_LEG_FAILURE_RANGES,
            MetricName.DATA_QUALITY_FAILURE_COUNT,
        )
    )
    outcome = evaluate_strategy_validation(
        _specification((_scheduled(slot),), required_metrics=references), (slot,)
    )
    assert outcome.status is StrategyValidationStatus.VALIDATED
    records = {item.reference.metric: item for item in outcome.result.metric_records}
    assert records[MetricName.DATA_QUALITY_FAILURE_COUNT].value == Decimal("0")
    for metric in references[:-1]:
        record = records[metric.metric]
        assert record.availability is MetricAvailability.AVAILABLE
        assert record.value is None
        assert "not silently pooled" in record.reason
    economics = outcome.result.observation_records[0].economics_result
    assert economics is not None
    assert economics.evaluation.total_purchase_cost is not None
    assert economics.evaluation.total_fee_interval is not None
    assert economics.evaluation.aggregate_gross_edge is not None
    assert economics.evaluation.aggregate_net_edge is not None
    assert economics.evaluation.residual_failures


def test_upstream_not_violated_is_not_a_data_quality_failure_and_zero_criterion_passes() -> None:
    satisfied = _complete_slot("satisfied", START, mode="unavailable")
    data_quality = MetricReference(MetricName.DATA_QUALITY_FAILURE_COUNT, None, None, ())
    specification = _specification(
        (_scheduled(satisfied),),
        required_metrics=(data_quality,),
        criteria=(
            AcceptanceCriterion(
                "zero-data-quality-failures",
                data_quality,
                ComparisonOperator.EQUAL,
                Decimal("0"),
            ),
        ),
    )
    outcome = evaluate_strategy_validation(specification, (satisfied,))
    metric = next(item for item in outcome.result.metric_records if item.reference == data_quality)
    status_counts = {item.status: item.count for item in outcome.result.status_metrics}
    reason_counts = {item.reason_code: item.count for item in outcome.result.reason_metrics}
    assert metric.value == Decimal("0")
    assert outcome.status is StrategyValidationStatus.VALIDATED
    assert outcome.record is not None
    assert is_trusted_historical_validation_record(outcome.record)
    assert status_counts[OpportunityEconomicsStatus.UNAVAILABLE] == 1
    assert reason_counts[OpportunityReasonCode.UPSTREAM_NOT_VIOLATED.value] == 1


def test_non_opportunity_statuses_are_not_data_quality_failures() -> None:
    slots = (
        _complete_slot("no-edge-quality", START, mode="no_net_edge"),
        _complete_slot(
            "depth-quality",
            START + timedelta(minutes=1),
            mode="insufficient_depth",
            quantity=Decimal("2"),
        ),
        _complete_slot(
            "direction-quality",
            START + timedelta(minutes=2),
            relationship=RelationshipType.IMPLICATION,
            mode="unsupported",
        ),
    )
    schedule = tuple(
        _scheduled(
            item,
            relationship=(
                RelationshipType.IMPLICATION
                if item.observation_id == "direction-quality"
                else RelationshipType.COMPLEMENT
            ),
        )
        for item in slots
    )
    data_quality = MetricReference(MetricName.DATA_QUALITY_FAILURE_COUNT, None, None, ())
    outcome = evaluate_strategy_validation(
        _specification(schedule, required_metrics=(data_quality,)), slots
    )
    metric = next(item for item in outcome.result.metric_records if item.reference == data_quality)
    counts = {item.status: item.count for item in outcome.result.status_metrics}
    assert metric.value == Decimal("0")
    assert counts[OpportunityEconomicsStatus.NO_NET_EDGE] == 1
    assert counts[OpportunityEconomicsStatus.INSUFFICIENT_DEPTH] == 1
    assert counts[OpportunityEconomicsStatus.UNSUPPORTED_TRADE_DIRECTION] == 1


def test_explicit_data_quality_failure_counts_once_and_gap_only_breaks_denominator() -> None:
    data_failure = ExplicitUnavailableSlot(
        "data-failure",
        START,
        UnavailabilityReason(
            UnavailabilityCode.DATA_QUALITY_FAILURE,
            "Synthetic historical data-quality failure.",
        ),
        (RawReference("diagnostics-data-failure", Venue.POLYMARKET),),
    )
    gap = _unavailable_slot("ordinary-gap", START + timedelta(minutes=1))
    schedule = (_scheduled(data_failure), _scheduled(gap))
    data_quality = MetricReference(MetricName.DATA_QUALITY_FAILURE_COUNT, None, None, ())
    outcome = evaluate_strategy_validation(
        _specification(schedule, required_metrics=(data_quality,)), (data_failure, gap)
    )
    metric = next(item for item in outcome.result.metric_records if item.reference == data_quality)
    reason_counts = {item.reason_code: item.count for item in outcome.result.reason_metrics}
    assert outcome.result.scheduled_count == 2
    assert outcome.result.validated_opportunity_frequency.denominator == 2
    assert metric.value == Decimal("1")
    assert reason_counts["schedule:data_quality_failure"] == 1
    assert reason_counts["schedule:explicit_schedule_gap"] == 1


def test_genuine_invalid_historical_observation_counts_once() -> None:
    malformed = _complete_slot("malformed-quality", START)
    snapshot = malformed.snapshots[0][1]
    object.__setattr__(snapshot.order_book.asks.levels[0], "size", "not-decimal")
    data_quality = MetricReference(MetricName.DATA_QUALITY_FAILURE_COUNT, None, None, ())
    outcome = evaluate_strategy_validation(
        _specification((_scheduled(malformed),), required_metrics=(data_quality,)),
        (malformed,),
    )
    metric = next(item for item in outcome.result.metric_records if item.reference == data_quality)
    assert outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert metric.value == Decimal("1")
    assert outcome.result.observation_records[0].economics_result is not None
    assert (
        outcome.result.observation_records[0].economics_result.evaluation.reasons[0].code
        is OpportunityReasonCode.INVALID_SNAPSHOT
    )


def test_multiple_qualifying_reasons_cannot_double_count_one_observation(monkeypatch) -> None:
    slot = _complete_slot("multiple-quality-reasons", START, mode="unavailable")
    data_quality = MetricReference(MetricName.DATA_QUALITY_FAILURE_COUNT, None, None, ())
    specification = _specification((_scheduled(slot),), required_metrics=(data_quality,))
    accepted = opportunities_api.evaluate_opportunity

    def multiple_reasons(
        certificate: object,
        constraint: object,
        snapshots: object,
        quantity: object,
        policies: object,
    ) -> OpportunityEconomicsResult:
        result = accepted(certificate, constraint, snapshots, quantity, policies)
        evaluation = replace(
            result.evaluation,
            reasons=(
                OpportunityReason(
                    OpportunityReasonCode.MISSING_SNAPSHOT,
                    "Synthetic missing historical snapshot.",
                ),
                OpportunityReason(
                    OpportunityReasonCode.INVALID_SNAPSHOT,
                    "Synthetic invalid historical snapshot.",
                ),
            ),
        )
        return OpportunityEconomicsResult(evaluation)

    monkeypatch.setattr(opportunities_api, "evaluate_opportunity", multiple_reasons)
    outcome = evaluate_strategy_validation(specification, (slot,))
    metric = next(item for item in outcome.result.metric_records if item.reference == data_quality)
    assert metric.value == Decimal("1")
    reason_counts = {item.reason_code: item.count for item in outcome.result.reason_metrics}
    assert reason_counts[OpportunityReasonCode.MISSING_SNAPSHOT.value] == 1
    assert reason_counts[OpportunityReasonCode.INVALID_SNAPSHOT.value] == 1


def test_scoped_data_quality_failure_counts_remain_exact() -> None:
    polymarket_failure = ExplicitUnavailableSlot(
        "poly-quality",
        START,
        UnavailabilityReason(
            UnavailabilityCode.DATA_QUALITY_FAILURE,
            "Synthetic Polymarket data-quality failure.",
        ),
        (RawReference("poly-quality", Venue.POLYMARKET),),
    )
    polymarket_gap = _unavailable_slot("poly-gap", START + timedelta(minutes=1))
    kalshi_failure = ExplicitUnavailableSlot(
        "kalshi-quality",
        START + timedelta(minutes=2),
        UnavailabilityReason(
            UnavailabilityCode.DATA_QUALITY_FAILURE,
            "Synthetic Kalshi data-quality failure.",
        ),
        (RawReference("kalshi-quality", Venue.KALSHI),),
    )
    slots = (polymarket_failure, polymarket_gap, kalshi_failure)
    schedule = (
        _scheduled(polymarket_failure, venue=Venue.POLYMARKET),
        _scheduled(polymarket_gap, venue=Venue.POLYMARKET),
        _scheduled(kalshi_failure, venue=Venue.KALSHI),
    )
    polymarket_metric = MetricReference(
        MetricName.DATA_QUALITY_FAILURE_COUNT,
        None,
        None,
        (("venue", Venue.POLYMARKET.value),),
    )
    kalshi_metric = MetricReference(
        MetricName.DATA_QUALITY_FAILURE_COUNT,
        None,
        None,
        (("venue", Venue.KALSHI.value),),
    )
    outcome = evaluate_strategy_validation(
        _specification(
            schedule,
            required_metrics=(polymarket_metric, kalshi_metric),
        ),
        slots,
    )
    values = {item.reference: item.value for item in outcome.result.metric_records}
    assert values[polymarket_metric] == Decimal("1")
    assert values[kalshi_metric] == Decimal("1")
    assert outcome.result.scheduled_count == 3


def test_financial_metric_criterion_without_aggregation_semantics_is_unavailable() -> None:
    slot = _complete_slot("financial-criterion", START)
    purchase_cost = MetricReference(MetricName.PURCHASE_COST, None, None, ())
    specification = _specification(
        (_scheduled(slot),),
        required_metrics=(purchase_cost,),
        criteria=(
            AcceptanceCriterion(
                "no-invented-pooling",
                purchase_cost,
                ComparisonOperator.LESS_THAN,
                Decimal("10"),
            ),
        ),
    )
    result = evaluate_strategy_validation(specification, (slot,))
    assert result.status is StrategyValidationStatus.UNAVAILABLE
    assert result.result.reasons[0].code is ValidationReasonCode.UNSUPPORTED_CRITERION_METRIC


@pytest.mark.parametrize("metric_name", ECONOMICS_DERIVED_METRICS)
def test_required_economics_metric_without_measurement_fails_closed(
    metric_name: MetricName,
) -> None:
    gap = _unavailable_slot("economics-gap", START)
    metric = MetricReference(metric_name, None, None, ())
    specification = _specification((_scheduled(gap),), required_metrics=(metric,))
    outcome = evaluate_strategy_validation(specification, (gap,))
    record = next(item for item in outcome.result.metric_records if item.reference == metric)
    assert outcome.result.scheduled_count == 1
    assert (
        sum(item.economics_result is not None for item in outcome.result.observation_records) == 0
    )
    assert record.availability is MetricAvailability.UNAVAILABLE
    assert record.value is None
    assert outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert outcome.result.reasons[0].code is ValidationReasonCode.UNSUPPORTED_REQUIRED_METRIC
    assert outcome.record is None


def test_scoped_economics_metric_cannot_borrow_measurement_from_another_stratum() -> None:
    measured = _complete_slot("measured-poly", START)
    unmeasured = _unavailable_slot("unmeasured-kalshi", START + timedelta(minutes=1))
    schedule = (
        _scheduled(measured, venue=Venue.POLYMARKET),
        _scheduled(unmeasured, venue=Venue.KALSHI),
    )
    metric = MetricReference(
        MetricName.PURCHASE_COST,
        None,
        None,
        (("venue", Venue.KALSHI.value),),
    )
    outcome = evaluate_strategy_validation(
        _specification(schedule, required_metrics=(metric,)),
        (measured, unmeasured),
    )
    record = next(item for item in outcome.result.metric_records if item.reference == metric)
    assert outcome.result.observation_records[0].economics_result is not None
    assert outcome.result.observation_records[1].economics_result is None
    assert record.availability is MetricAvailability.UNAVAILABLE
    assert record.value is None
    assert outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert outcome.record is None


@pytest.mark.parametrize("metric_name", ECONOMICS_DERIVED_METRICS)
def test_applicable_economics_measurement_remains_available_without_pooling(
    metric_name: MetricName,
) -> None:
    slot = _complete_slot(f"measured-{metric_name.value}", START)
    metric = MetricReference(metric_name, None, None, ())
    specification = _specification((_scheduled(slot),), required_metrics=(metric,))
    first = evaluate_strategy_validation(specification, (slot,))
    second = evaluate_strategy_validation(specification, (slot,))
    record = next(item for item in first.result.metric_records if item.reference == metric)
    economics = first.result.observation_records[0].economics_result
    assert economics is not None
    assert record.availability is MetricAvailability.AVAILABLE
    assert record.value is None
    assert "not silently pooled" in record.reason
    assert first.status is StrategyValidationStatus.VALIDATED
    assert first.record is not None and is_trusted_historical_validation_record(first.record)
    assert first.result.validation_id == second.result.validation_id
    assert stable_json_bytes(first.result) == stable_json_bytes(second.result)


def test_requested_quantity_remains_available_from_unavailable_schedule_slot() -> None:
    gap = _unavailable_slot("quantity-gap", START)
    metric = MetricReference(MetricName.REQUESTED_QUANTITY, None, None, ())
    outcome = evaluate_strategy_validation(
        _specification((_scheduled(gap),), required_metrics=(metric,)),
        (gap,),
    )
    record = next(item for item in outcome.result.metric_records if item.reference == metric)
    assert outcome.result.observation_records[0].scheduled.quantity == Decimal("1")
    assert record.availability is MetricAvailability.AVAILABLE
    assert record.value is None
    assert "preserved in the schedule" in record.reason


def test_mutation_and_reconstruction_cannot_bypass_economics_availability() -> None:
    gap = _unavailable_slot("bypass-gap", START)
    requested_quantity = MetricReference(MetricName.REQUESTED_QUANTITY, None, None, ())
    purchase_cost = MetricReference(MetricName.PURCHASE_COST, None, None, ())
    mutated = _specification((_scheduled(gap),), required_metrics=(requested_quantity,))
    object.__setattr__(mutated, "required_metrics", (purchase_cost,))
    mutated_outcome = evaluate_strategy_validation(mutated, (gap,))
    assert mutated_outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert mutated_outcome.result.reasons[0].code is ValidationReasonCode.INVALID_SPECIFICATION
    assert mutated_outcome.record is None

    reconstructed = _specification((_scheduled(gap),), required_metrics=(purchase_cost,))
    reconstructed_outcome = evaluate_strategy_validation(reconstructed, (gap,))
    metric_record = next(
        item
        for item in reconstructed_outcome.result.metric_records
        if item.reference == purchase_cost
    )
    assert metric_record.availability is MetricAvailability.UNAVAILABLE
    assert reconstructed_outcome.status is StrategyValidationStatus.UNAVAILABLE
    assert reconstructed_outcome.record is None


def test_success_record_process_local_trust_and_nontransfer() -> None:
    outcome = _validated_outcome()
    record = outcome.historical_record
    assert record is not None and is_trusted_historical_validation_record(record)
    assert record.historical is True and record.non_actionable is True
    assert not any(
        (
            record.future_profit_claim,
            record.execution_supported,
            record.simulation_supported,
            record.risk_authorized,
            record.trade_authorized,
        )
    )
    serialized = stable_json_bytes(record)
    assert b"trust" not in serialized.lower()
    for clone in (copy.copy(record), copy.deepcopy(record), pickle.loads(pickle.dumps(record))):
        assert not is_trusted_historical_validation_record(clone)
    assert not is_trusted_historical_validation_record(json.loads(serialized))

    fake = object.__new__(SuccessfulHistoricalValidationRecord)
    for name in (
        "schema_version",
        "record_id",
        "validation_result",
        "historical",
        "non_actionable",
        "statement",
        "future_profit_claim",
        "execution_supported",
        "simulation_supported",
        "risk_authorized",
        "trade_authorized",
    ):
        object.__setattr__(fake, name, getattr(record, name))
    assert not is_trusted_historical_validation_record(fake)

    class RecordSubclass(SuccessfulHistoricalValidationRecord):
        pass

    subclass = object.__new__(RecordSubclass)
    assert not is_trusted_historical_validation_record(subclass)
    object.__setattr__(record, "non_actionable", False)
    assert not is_trusted_historical_validation_record(record)


def test_specification_dataset_and_report_identities_are_deterministic() -> None:
    slots = (
        _complete_slot("identity-1", START),
        _complete_slot("identity-2", START + timedelta(minutes=1)),
    )
    schedule = tuple(_scheduled(item) for item in slots)
    first_specification = _specification(schedule)
    second_specification = _specification(schedule)
    first = evaluate_strategy_validation(first_specification, slots).result
    second = evaluate_strategy_validation(second_specification, slots).result
    assert first_specification.specification_id.startswith("strategy-specification:")
    assert first.dataset_id.startswith("strategy-validation-dataset:")
    assert first.validation_id.startswith("strategy-validation:")
    assert first_specification.specification_id == second_specification.specification_id
    assert first.dataset_id == second.dataset_id
    assert first.validation_id == second.validation_id
    assert stable_json_bytes(first) == stable_json_bytes(second)


def test_nonvalidated_statuses_never_issue_success_record() -> None:
    slot = _complete_slot("failed", START)
    count = MetricReference(MetricName.SCHEDULED_COUNT, None, None, ())
    criteria_spec = _specification(
        (_scheduled(slot),),
        required_metrics=(count,),
        criteria=(
            AcceptanceCriterion("fail", count, ComparisonOperator.GREATER_THAN, Decimal("1")),
        ),
    )
    criteria = evaluate_strategy_validation(criteria_spec, (slot,))
    assert criteria.status is StrategyValidationStatus.CRITERIA_NOT_MET
    assert criteria.historical_record is None
    unavailable = evaluate_strategy_validation(criteria_spec, ())
    assert unavailable.status is StrategyValidationStatus.UNAVAILABLE
    assert unavailable.historical_record is None


def test_weak_trust_registry_self_prunes_after_garbage_collection() -> None:
    baseline = len(_TRUSTED_HISTORICAL_RECORDS)
    outcome = _validated_outcome()
    record = outcome.historical_record
    assert record is not None
    reference = weakref.ref(record)
    assert len(_TRUSTED_HISTORICAL_RECORDS) == baseline + 1
    del record
    del outcome
    gc.collect()
    assert reference() is None
    assert len(_TRUSTED_HISTORICAL_RECORDS) == baseline


def test_diagnostics_attempts_no_network(monkeypatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("historical diagnostics attempted an outbound socket")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    assert _validated_outcome().status is StrategyValidationStatus.VALIDATED


def test_hash_seed_identity_order_and_serialization_are_stable() -> None:
    script = """
import importlib.util
from pathlib import Path
from invariant_engine.serialization import stable_json_bytes

path = Path('tests/diagnostics/test_strategy_validation.py').resolve()
spec = importlib.util.spec_from_file_location('diagnostics_hash_seed', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
outcome = module._validated_outcome()
print(outcome.result.validation_id)
print(outcome.historical_record.record_id)
print(stable_json_bytes(outcome.result).decode())
"""
    outputs = []
    for seed in ("1", "2", "random"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(ROOT / "src")
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script], cwd=ROOT, env=environment, text=True
            )
        )
    assert outputs[0] == outputs[1] == outputs[2]


def test_no_simulation_risk_execution_or_trading_claims() -> None:
    result = _validated_outcome().result
    assert result.historical is True
    assert result.non_actionable is True
    assert result.future_profit_claim is False
    assert result.execution_supported is False
    assert result.simulation_supported is False
    assert result.risk_authorized is False
    assert result.trade_authorized is False
    assert len(result.unsupported_metrics) == 11
    assert all(
        item.availability is MetricAvailability.UNAVAILABLE for item in result.unsupported_metrics
    )
