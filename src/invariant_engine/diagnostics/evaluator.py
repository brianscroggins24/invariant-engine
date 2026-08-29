"""Deterministic aggregation of independently reconstructed Milestone 3 results."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace
from decimal import Context, Decimal, localcontext
from typing import cast

import invariant_engine.opportunities as opportunities_api
from invariant_engine.opportunities import (
    OpportunityEconomicsStatus,
    OpportunityReasonCode,
)
from invariant_engine.serialization import stable_json_bytes

from .models import (
    _HISTORICAL_RECORD_TRUST_TOKEN,
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    UNSUPPORTED_METRICS,
    AcceptanceCriterion,
    ComparisonOperator,
    CompleteObservationSlot,
    CriterionOutcome,
    Eligibility,
    EvidenceMinimum,
    EvidenceMinimumOutcome,
    ExplicitUnavailableSlot,
    MetricAvailability,
    MetricName,
    MetricRecord,
    MetricReference,
    ObservationValidationRecord,
    PersistenceRun,
    Ratio,
    ReasonMetric,
    RuntimeObservationSlot,
    ScheduledObservation,
    StatusMetric,
    StrategyValidationEvaluation,
    StrategyValidationResult,
    StrategyValidationSpecification,
    StrategyValidationStatus,
    StratumResult,
    SuccessfulHistoricalValidationRecord,
    UnavailabilityCode,
    UnsupportedMetricRecord,
    ValidationReason,
    ValidationReasonCode,
)

_M3_CONTEXT = Context(prec=28, rounding="ROUND_HALF_EVEN")

_MALFORMED_UPSTREAM_REASONS = frozenset(
    {
        OpportunityReasonCode.WRONG_TYPE,
        OpportunityReasonCode.INVALID_CERTIFICATE,
        OpportunityReasonCode.INVALID_CONSTRAINT,
        OpportunityReasonCode.CONSTRAINT_MISMATCH,
        OpportunityReasonCode.INVALID_QUANTITY,
        OpportunityReasonCode.MISSING_SNAPSHOT,
        OpportunityReasonCode.EXTRA_SNAPSHOT,
        OpportunityReasonCode.INVALID_SNAPSHOT,
        OpportunityReasonCode.MISSING_FEE_POLICY,
        OpportunityReasonCode.DUPLICATE_FEE_POLICY,
        OpportunityReasonCode.INVALID_FEE_POLICY,
        OpportunityReasonCode.INTERNAL_REPRESENTATION,
    }
)

_DATA_QUALITY_REASON_CODES = frozenset(
    {
        OpportunityReasonCode.MISSING_SNAPSHOT,
        OpportunityReasonCode.EXTRA_SNAPSHOT,
        OpportunityReasonCode.INVALID_SNAPSHOT,
        OpportunityReasonCode.OBSERVATION_FAILURE,
        OpportunityReasonCode.MISSING_FEE_POLICY,
        OpportunityReasonCode.DUPLICATE_FEE_POLICY,
        OpportunityReasonCode.INVALID_FEE_POLICY,
        OpportunityReasonCode.INEFFECTIVE_FEE_POLICY,
        OpportunityReasonCode.CURRENCY_INCOMPATIBLE,
    }
)


def _validated_specification(value: object) -> StrategyValidationSpecification:
    if type(value) is not StrategyValidationSpecification:
        raise ValueError("strategy validation requires an exact specification")
    specification = value
    rebuilt_schedule = tuple(replace(item) for item in specification.schedule)
    rebuilt_inclusion = tuple(replace(item) for item in specification.inclusion_rules)
    rebuilt_exclusion = tuple(replace(item) for item in specification.exclusion_rules)
    rebuilt_partitions = tuple(replace(item) for item in specification.partitions)
    rebuilt_required = tuple(replace(item) for item in specification.required_metrics)
    rebuilt_minimums = tuple(
        EvidenceMinimum(
            item.minimum_id,
            replace(item.metric),
            item.minimum,
        )
        for item in specification.evidence_minimums
    )
    rebuilt_criteria = tuple(
        AcceptanceCriterion(
            item.criterion_id,
            replace(item.metric),
            item.operator,
            item.threshold,
        )
        for item in specification.acceptance_criteria
    )
    rebuilt = StrategyValidationSpecification(
        schema_version=specification.schema_version,
        strategy_id=specification.strategy_id,
        strategy_version=specification.strategy_version,
        analysis_start=specification.analysis_start,
        analysis_end=specification.analysis_end,
        start_inclusive=specification.start_inclusive,
        end_inclusive=specification.end_inclusive,
        included_relationship_classes=specification.included_relationship_classes,
        schedule=rebuilt_schedule,
        sampling_semantics=specification.sampling_semantics,
        grouping_key=specification.grouping_key,
        grouping_semantics=specification.grouping_semantics,
        stratification_keys=specification.stratification_keys,
        inclusion_rules=rebuilt_inclusion,
        exclusion_rules=rebuilt_exclusion,
        denominator_semantics=specification.denominator_semantics,
        gap_treatment=specification.gap_treatment,
        partitions=rebuilt_partitions,
        required_metrics=rebuilt_required,
        evidence_minimums=rebuilt_minimums,
        acceptance_criteria=rebuilt_criteria,
        ratio_precision=specification.ratio_precision,
        rounding_mode=specification.rounding_mode,
        provenance=specification.provenance,
    )
    if stable_json_bytes(rebuilt) != stable_json_bytes(specification):
        raise ValueError("specification material changed after validation")
    allowed_scopes: set[tuple[tuple[str, str], ...]] = {()}
    for scheduled in specification.schedule:
        pairs = {
            *scheduled.strata,
            ("partition", scheduled.partition_id or "unpartitioned"),
            ("grouping_identity", scheduled.grouping_identity),
        }
        for reference in (
            *specification.required_metrics,
            *(item.metric for item in specification.evidence_minimums),
            *(item.metric for item in specification.acceptance_criteria),
        ):
            if all(item in pairs for item in reference.scope):
                allowed_scopes.add(reference.scope)
    references = (
        *specification.required_metrics,
        *(item.metric for item in specification.evidence_minimums),
        *(item.metric for item in specification.acceptance_criteria),
    )
    if any(reference.scope not in allowed_scopes for reference in references):
        raise ValueError("metric scope is not represented by the fixed schedule")
    return specification


def _validated_slot(value: object) -> RuntimeObservationSlot:
    rebuilt: RuntimeObservationSlot
    if type(value) is CompleteObservationSlot:
        complete_slot = value
        rebuilt = CompleteObservationSlot(
            observation_id=complete_slot.observation_id,
            timestamp=complete_slot.timestamp,
            certificate=complete_slot.certificate,
            constraint=complete_slot.constraint,
            snapshots=complete_slot.snapshots,
            quantity=complete_slot.quantity,
            fee_policies=complete_slot.fee_policies,
            provenance=complete_slot.provenance,
        )
    elif type(value) is ExplicitUnavailableSlot:
        unavailable_slot = value
        rebuilt = ExplicitUnavailableSlot(
            observation_id=unavailable_slot.observation_id,
            timestamp=unavailable_slot.timestamp,
            reason=replace(unavailable_slot.reason),
            provenance=unavailable_slot.provenance,
        )
    else:
        raise ValueError("runtime schedule contains a non-slot object")
    if stable_json_bytes(rebuilt) != stable_json_bytes(value):
        raise ValueError("runtime slot material changed after construction")
    return rebuilt


def _ratio(
    numerator: int, denominator: int, specification: StrategyValidationSpecification
) -> Ratio:
    if denominator == 0:
        return Ratio(numerator, denominator, None)
    context = Context(prec=specification.ratio_precision, rounding=specification.rounding_mode)
    with localcontext(context):
        value = Decimal(numerator) / Decimal(denominator)
    return Ratio(numerator, denominator, value)


def _material_fingerprint(slot: CompleteObservationSlot) -> str:
    material = {
        "certificate": slot.certificate,
        "constraint": slot.constraint,
        "snapshots": slot.snapshots,
        "quantity": slot.quantity,
        "fee_policies": slot.fee_policies,
    }
    return hashlib.sha256(stable_json_bytes(material)).hexdigest()


def _scope_matches(scheduled: ScheduledObservation, scope: tuple[tuple[str, str], ...]) -> bool:
    values = {
        *scheduled.strata,
        ("partition", scheduled.partition_id or "unpartitioned"),
        ("grouping_identity", scheduled.grouping_identity),
    }
    return all(item in values for item in scope)


def _selected(
    records: tuple[ObservationValidationRecord, ...], scope: tuple[tuple[str, str], ...]
) -> tuple[ObservationValidationRecord, ...]:
    return tuple(item for item in records if _scope_matches(item.scheduled, scope))


def _status_metrics(
    records: tuple[ObservationValidationRecord, ...], specification: StrategyValidationSpecification
) -> tuple[StatusMetric, ...]:
    counts = Counter(item.effective_status for item in records)
    denominator = len(records)
    return tuple(
        StatusMetric(status, counts[status], _ratio(counts[status], denominator, specification))
        for status in OpportunityEconomicsStatus
    )


def _reason_counts(records: tuple[ObservationValidationRecord, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        if record.economics_result is None:
            slot = cast(ExplicitUnavailableSlot, record.supplied_slot)
            counts[f"schedule:{slot.reason.code.value}"] += 1
        else:
            for reason in record.economics_result.evaluation.reasons:
                counts[reason.code.value] += 1
    return counts


def _reason_metrics(
    records: tuple[ObservationValidationRecord, ...], specification: StrategyValidationSpecification
) -> tuple[ReasonMetric, ...]:
    counts = _reason_counts(records)
    known = [item.value for item in OpportunityReasonCode]
    extras = sorted(set(counts) - set(known))
    denominator = len(records)
    return tuple(
        ReasonMetric(code, counts[code], _ratio(counts[code], denominator, specification))
        for code in (*known, *extras)
    )


def _persistence(
    records: tuple[ObservationValidationRecord, ...],
) -> tuple[PersistenceRun, ...]:
    groups: list[str] = []
    for item in records:
        if item.scheduled.grouping_identity not in groups:
            groups.append(item.scheduled.grouping_identity)
    runs: list[PersistenceRun] = []
    for group in groups:
        current: list[ObservationValidationRecord] = []
        for item in records:
            if item.scheduled.grouping_identity != group:
                continue
            if item.effective_status is OpportunityEconomicsStatus.VALIDATED:
                current.append(item)
            else:
                if current:
                    runs.append(_persistence_run(group, current))
                    current = []
        if current:
            runs.append(_persistence_run(group, current))
    return tuple(runs)


def _persistence_run(
    grouping_identity: str, records: list[ObservationValidationRecord]
) -> PersistenceRun:
    start = records[0].scheduled.timestamp
    end = records[-1].scheduled.timestamp
    duration = end - start
    duration_seconds = Decimal(duration.days * 86400 + duration.seconds) + Decimal(
        duration.microseconds
    ) / Decimal("1000000")
    return PersistenceRun(
        grouping_identity=grouping_identity,
        observation_ids=tuple(item.scheduled.observation_id for item in records),
        start_timestamp=start,
        end_timestamp=end,
        observation_count=len(records),
        observed_duration=duration_seconds,
    )


def _strata(
    records: tuple[ObservationValidationRecord, ...], specification: StrategyValidationSpecification
) -> tuple[StratumResult, ...]:
    scopes: list[tuple[tuple[str, str], ...]] = [()]
    for item in records:
        candidates = (
            item.scheduled.strata,
            (("partition", item.scheduled.partition_id or "unpartitioned"),),
            (("grouping_identity", item.scheduled.grouping_identity),),
        )
        for scope in candidates:
            if scope not in scopes:
                scopes.append(scope)
    result: list[StratumResult] = []
    for scope in scopes:
        selected = _selected(records, scope)
        validated = sum(
            item.effective_status is OpportunityEconomicsStatus.VALIDATED for item in selected
        )
        eligible = sum(item.scheduled.eligibility is Eligibility.INCLUDED for item in selected)
        result.append(
            StratumResult(
                scope=scope,
                scheduled_count=len(selected),
                eligible_count=eligible,
                ineligible_count=len(selected) - eligible,
                status_metrics=_status_metrics(selected, specification),
                reason_metrics=_reason_metrics(selected, specification),
                validated_opportunity_frequency=_ratio(validated, len(selected), specification),
            )
        )
    return tuple(result)


def _metric_value(
    reference: MetricReference,
    records: tuple[ObservationValidationRecord, ...],
    persistence: tuple[PersistenceRun, ...],
    specification: StrategyValidationSpecification,
) -> MetricRecord:
    if reference.metric in UNSUPPORTED_METRICS:
        return MetricRecord(
            reference,
            MetricAvailability.UNAVAILABLE,
            None,
            None,
            None,
            "metric is outside authorized historical measurement semantics",
        )
    selected = _selected(records, reference.scope)
    denominator = len(selected)
    count: int
    if reference.metric is MetricName.SCHEDULED_COUNT:
        count = denominator
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    if reference.metric is MetricName.ELIGIBLE_COUNT:
        count = sum(item.scheduled.eligibility is Eligibility.INCLUDED for item in selected)
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    if reference.metric is MetricName.INELIGIBLE_COUNT:
        count = sum(item.scheduled.eligibility is Eligibility.EXCLUDED for item in selected)
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    if reference.metric in (MetricName.STATUS_COUNT, MetricName.STATUS_RATE):
        count = sum(item.effective_status is reference.status for item in selected)
    elif reference.metric in (MetricName.REASON_COUNT, MetricName.REASON_RATE):
        count = _reason_counts(selected)[cast(str, reference.reason_code)]
    elif reference.metric is MetricName.VALIDATED_OPPORTUNITY_FREQUENCY:
        count = sum(
            item.effective_status is OpportunityEconomicsStatus.VALIDATED for item in selected
        )
    elif reference.metric is MetricName.MAX_PERSISTENCE_OBSERVATIONS:
        applicable = tuple(
            run
            for run in persistence
            if any(
                record.scheduled.grouping_identity == run.grouping_identity
                and _scope_matches(record.scheduled, reference.scope)
                for record in selected
            )
        )
        count = max((item.observation_count for item in applicable), default=0)
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    elif reference.metric is MetricName.DATA_QUALITY_FAILURE_COUNT:
        count = sum(_is_data_quality_failure(item) for item in selected)
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    elif reference.metric is MetricName.REQUESTED_QUANTITY:
        if not selected:
            return MetricRecord(
                reference,
                MetricAvailability.UNAVAILABLE,
                None,
                None,
                None,
                "the exact metric scope contains no scheduled quantities",
            )
        return MetricRecord(
            reference,
            MetricAvailability.AVAILABLE,
            None,
            None,
            None,
            "exact requested quantities are preserved in the schedule and are not silently pooled",
        )
    elif reference.metric in {
        MetricName.OBSERVED_DEPTH_DIAGNOSTICS,
        MetricName.PURCHASE_COST,
        MetricName.FEE_INTERVAL,
        MetricName.GROSS_EDGE_INTERVAL,
        MetricName.NET_EDGE_INTERVAL,
        MetricName.RESIDUAL_SINGLE_LEG_FAILURE_RANGES,
    }:
        if not any(_has_economics_measurement(item, reference.metric) for item in selected):
            return MetricRecord(
                reference,
                MetricAvailability.UNAVAILABLE,
                None,
                None,
                None,
                "no selected observation contains the required per-observation "
                "economics measurement",
            )
        return MetricRecord(
            reference,
            MetricAvailability.AVAILABLE,
            None,
            None,
            None,
            "exact values are preserved per observation and are not silently pooled",
        )
    else:
        return MetricRecord(
            reference,
            MetricAvailability.UNAVAILABLE,
            None,
            None,
            None,
            "supported metric resolver is unavailable",
        )
    if reference.metric in (MetricName.STATUS_COUNT, MetricName.REASON_COUNT):
        return MetricRecord(reference, MetricAvailability.AVAILABLE, Decimal(count), count, 1, None)
    ratio = _ratio(count, denominator, specification)
    if ratio.decimal is None:
        return MetricRecord(
            reference,
            MetricAvailability.UNAVAILABLE,
            None,
            count,
            denominator,
            "metric scope has a zero denominator",
        )
    return MetricRecord(
        reference,
        MetricAvailability.AVAILABLE,
        ratio.decimal,
        count,
        denominator,
        None,
    )


def _is_data_quality_failure(record: ObservationValidationRecord) -> bool:
    if type(record.supplied_slot) is ExplicitUnavailableSlot:
        return record.supplied_slot.reason.code is UnavailabilityCode.DATA_QUALITY_FAILURE
    economics = record.economics_result
    if economics is None:
        return False
    return any(reason.code in _DATA_QUALITY_REASON_CODES for reason in economics.evaluation.reasons)


def _has_economics_measurement(record: ObservationValidationRecord, metric: MetricName) -> bool:
    economics = record.economics_result
    if economics is None:
        return False
    evaluation = economics.evaluation
    if metric is MetricName.OBSERVED_DEPTH_DIAGNOSTICS:
        return bool(evaluation.legs)
    if metric is MetricName.PURCHASE_COST:
        return evaluation.total_purchase_cost is not None
    if metric is MetricName.FEE_INTERVAL:
        return evaluation.total_fee_interval is not None
    if metric is MetricName.GROSS_EDGE_INTERVAL:
        return evaluation.aggregate_gross_edge is not None
    if metric is MetricName.NET_EDGE_INTERVAL:
        return evaluation.aggregate_net_edge is not None
    if metric is MetricName.RESIDUAL_SINGLE_LEG_FAILURE_RANGES:
        return bool(evaluation.residual_failures)
    return False


def _compare(actual: Decimal, operator: ComparisonOperator, threshold: Decimal) -> bool:
    if operator is ComparisonOperator.LESS_THAN:
        return actual < threshold
    if operator is ComparisonOperator.LESS_THAN_OR_EQUAL:
        return actual <= threshold
    if operator is ComparisonOperator.EQUAL:
        return actual == threshold
    if operator is ComparisonOperator.GREATER_THAN_OR_EQUAL:
        return actual >= threshold
    if operator is ComparisonOperator.GREATER_THAN:
        return actual > threshold
    return False


def _unsupported_records() -> tuple[UnsupportedMetricRecord, ...]:
    reasons = {
        MetricName.LATENCY: "latency semantics are unavailable and Milestone 6 is inactive",
        MetricName.QUEUE_POSITION: "queue-position semantics are unavailable",
        MetricName.FILL_PROBABILITY: "fill probability is not evaluated",
        MetricName.PARTIAL_FILLS: "partial-fill behavior is not evaluated",
        MetricName.CANCELLATION: "cancellation behavior is not evaluated",
        MetricName.EXECUTION_SEQUENCING: "execution sequencing is not evaluated",
        MetricName.FALSE_RELATIONSHIP_GROUND_TRUTH: "no governed labeled benchmark exists",
        MetricName.PORTFOLIO_CAPITAL_ALLOCATION: "portfolio capital allocation is not authorized",
        MetricName.CONCURRENT_CAPITAL_USAGE: "concurrent capital usage is not evaluated",
        MetricName.REALIZED_PORTFOLIO_PNL: "realized portfolio PnL is not evaluated",
        MetricName.DRAWDOWNS: "drawdowns are not evaluated",
    }
    return tuple(
        UnsupportedMetricRecord(metric, MetricAvailability.UNAVAILABLE, reasons[metric])
        for metric in UNSUPPORTED_METRICS
    )


def _empty_ratio() -> Ratio:
    return Ratio(0, 0, None)


def _make_result(
    *,
    status: StrategyValidationStatus,
    specification: StrategyValidationSpecification | None,
    records: tuple[ObservationValidationRecord, ...] = (),
    status_metrics: tuple[StatusMetric, ...] = (),
    reason_metrics: tuple[ReasonMetric, ...] = (),
    frequency: Ratio | None = None,
    persistence: tuple[PersistenceRun, ...] = (),
    strata: tuple[StratumResult, ...] = (),
    metric_records: tuple[MetricRecord, ...] = (),
    evidence: tuple[EvidenceMinimumOutcome, ...] = (),
    criteria: tuple[CriterionOutcome, ...] = (),
    reasons: tuple[ValidationReason, ...] = (),
) -> StrategyValidationResult:
    scheduled_count = len(specification.schedule) if specification is not None else 0
    eligible_count = (
        sum(item.eligibility is Eligibility.INCLUDED for item in specification.schedule)
        if specification is not None
        else 0
    )
    provenance = specification.provenance if specification is not None else ()
    content = {
        "schema_version": STRATEGY_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "specification": specification,
        "observation_records": records,
        "scheduled_count": scheduled_count,
        "eligible_count": eligible_count,
        "ineligible_count": scheduled_count - eligible_count,
        "status_metrics": status_metrics,
        "reason_metrics": reason_metrics,
        "validated_opportunity_frequency": frequency or _empty_ratio(),
        "persistence_runs": persistence,
        "strata": strata,
        "metric_records": metric_records,
        "evidence_outcomes": evidence,
        "criterion_outcomes": criteria,
        "unsupported_metrics": _unsupported_records(),
        "reasons": reasons,
        "provenance": provenance,
        "historical": True,
        "non_actionable": True,
        "future_profit_claim": False,
        "execution_supported": False,
        "simulation_supported": False,
        "risk_authorized": False,
        "trade_authorized": False,
    }
    dataset_content = {
        "specification_id": (specification.specification_id if specification is not None else None),
        "observation_records": records,
        "reasons": reasons,
    }
    dataset_id = (
        "strategy-validation-dataset:"
        + hashlib.sha256(stable_json_bytes(dataset_content)).hexdigest()
    )
    digest = hashlib.sha256(stable_json_bytes(content)).hexdigest()
    return StrategyValidationResult(
        validation_id="strategy-validation:" + digest,
        dataset_id=dataset_id,
        **content,  # type: ignore[arg-type]
    )


def _unavailable(
    reason: ValidationReason, specification: StrategyValidationSpecification | None = None
) -> StrategyValidationEvaluation:
    result = _make_result(
        status=StrategyValidationStatus.UNAVAILABLE,
        specification=specification,
        reasons=(reason,),
    )
    return StrategyValidationEvaluation(result, None)


def evaluate_strategy_validation(
    specification: object,
    runtime_slots: object,
    *,
    opportunity_evaluations: object | None = None,
    opportunity_results: object | None = None,
    opportunity_candidates: object | None = None,
    prior_reports: object | None = None,
) -> StrategyValidationEvaluation:
    """Validate one fixed historical strategy schedule without trusting later artifacts.

    Optional supplied Milestone 3 or prior-report values are deliberately ignored;
    only genuine upstream slot material is used to independently invoke the public
    Milestone 3 evaluator for every complete scheduled observation.
    """

    del opportunity_evaluations, opportunity_results, opportunity_candidates, prior_reports
    try:
        validated_spec = _validated_specification(specification)
    except Exception as exc:
        return _unavailable(
            ValidationReason(
                ValidationReasonCode.INVALID_SPECIFICATION,
                f"invalid immutable strategy specification: {exc}",
            )
        )
    try:
        if type(runtime_slots) is not tuple:
            raise ValueError("runtime schedule must be an immutable tuple")
        raw_slots = cast(tuple[object, ...], runtime_slots)
        slots = tuple(_validated_slot(item) for item in raw_slots)
    except Exception as exc:
        return _unavailable(
            ValidationReason(
                ValidationReasonCode.INVALID_RUNTIME_SLOT,
                f"invalid immutable runtime slot: {exc}",
            ),
            validated_spec,
        )
    expected = validated_spec.schedule
    if len(slots) != len(expected):
        return _unavailable(
            ValidationReason(
                ValidationReasonCode.SCHEDULE_MISMATCH,
                "runtime slots must represent every specification slot exactly once",
            ),
            validated_spec,
        )
    runtime_ids = tuple(item.observation_id for item in slots)
    if len(set(runtime_ids)) != len(runtime_ids):
        return _unavailable(
            ValidationReason(
                ValidationReasonCode.DUPLICATE_OBSERVATION_ID,
                "runtime observation IDs must be unique",
            ),
            validated_spec,
        )
    for scheduled, slot in zip(expected, slots, strict=True):
        if scheduled.observation_id != slot.observation_id or scheduled.timestamp != slot.timestamp:
            return _unavailable(
                ValidationReason(
                    ValidationReasonCode.SCHEDULE_MISMATCH,
                    "runtime IDs, timestamps, and order must exactly match the specification",
                    slot.observation_id,
                ),
                validated_spec,
            )
        if type(slot) is CompleteObservationSlot:
            complete = slot
            if complete.quantity != scheduled.quantity:
                return _unavailable(
                    ValidationReason(
                        ValidationReasonCode.QUANTITY_MISMATCH,
                        "runtime quantity differs from the fixed caller-supplied quantity",
                        slot.observation_id,
                    ),
                    validated_spec,
                )
            relationship = complete.certificate.proposed_relationship.relationship_type
            if relationship is not scheduled.relationship_class:
                return _unavailable(
                    ValidationReason(
                        ValidationReasonCode.RELATIONSHIP_CLASS_MISMATCH,
                        "runtime certificate relationship class differs from the schedule",
                        slot.observation_id,
                    ),
                    validated_spec,
                )
    fingerprints: dict[str, ScheduledObservation] = {}
    slot_fingerprints: dict[str, str] = {}
    for scheduled, slot in zip(expected, slots, strict=True):
        if type(slot) is not CompleteObservationSlot:
            continue
        try:
            fingerprint = _material_fingerprint(slot)
        except Exception as exc:
            return _unavailable(
                ValidationReason(
                    ValidationReasonCode.INVALID_RUNTIME_SLOT,
                    f"historical material cannot be deterministically fingerprinted: {exc}",
                    scheduled.observation_id,
                ),
                validated_spec,
            )
        previous = fingerprints.get(fingerprint)
        if previous is not None:
            code = (
                ValidationReasonCode.CROSS_PARTITION_MATERIAL_REUSE
                if previous.partition_id != scheduled.partition_id
                else ValidationReasonCode.DUPLICATE_MATERIAL
            )
            return _unavailable(
                ValidationReason(
                    code,
                    "identical historical material is hidden behind distinct observation IDs",
                    scheduled.observation_id,
                ),
                validated_spec,
            )
        fingerprints[fingerprint] = scheduled
        slot_fingerprints[scheduled.observation_id] = fingerprint

    records: list[ObservationValidationRecord] = []
    fatal_reasons: list[ValidationReason] = []
    for scheduled, slot in zip(expected, slots, strict=True):
        if type(slot) is ExplicitUnavailableSlot:
            unavailable = slot
            records.append(
                ObservationValidationRecord(
                    scheduled,
                    unavailable,
                    None,
                    None,
                    OpportunityEconomicsStatus.UNAVAILABLE,
                    unavailable.provenance,
                )
            )
            continue
        complete = cast(CompleteObservationSlot, slot)
        with localcontext(_M3_CONTEXT):
            economics = opportunities_api.evaluate_opportunity(
                complete.certificate,
                complete.constraint,
                complete.snapshots,
                complete.quantity,
                complete.fee_policies,
            )
        evaluation = economics.evaluation
        provenance = tuple(dict.fromkeys((*complete.provenance, *evaluation.combined_provenance)))
        records.append(
            ObservationValidationRecord(
                scheduled,
                complete,
                slot_fingerprints[scheduled.observation_id],
                economics,
                economics.status,
                provenance,
            )
        )
        if (
            evaluation.common_timestamp is not None
            and evaluation.common_timestamp != scheduled.timestamp
        ):
            fatal_reasons.append(
                ValidationReason(
                    ValidationReasonCode.TEMPORAL_LEAKAGE,
                    "fresh Milestone 3 observation timestamp differs from the fixed schedule",
                    scheduled.observation_id,
                )
            )
        malformed = tuple(
            reason for reason in evaluation.reasons if reason.code in _MALFORMED_UPSTREAM_REASONS
        )
        if malformed:
            fatal_reasons.append(
                ValidationReason(
                    ValidationReasonCode.UNTRUSTED_UPSTREAM,
                    "fresh Milestone 3 rerun rejected malformed or untrusted upstream material",
                    scheduled.observation_id,
                )
            )

    immutable_records = tuple(records)
    status_metrics = _status_metrics(immutable_records, validated_spec)
    reason_metrics = _reason_metrics(immutable_records, validated_spec)
    validated_count = sum(
        item.effective_status is OpportunityEconomicsStatus.VALIDATED for item in immutable_records
    )
    frequency = _ratio(validated_count, len(immutable_records), validated_spec)
    persistence = _persistence(immutable_records)
    strata = _strata(immutable_records, validated_spec)
    all_references: list[MetricReference] = []
    for reference in (
        *validated_spec.required_metrics,
        *(item.metric for item in validated_spec.evidence_minimums),
        *(item.metric for item in validated_spec.acceptance_criteria),
    ):
        if reference not in all_references:
            all_references.append(reference)
    metrics = tuple(
        _metric_value(reference, immutable_records, persistence, validated_spec)
        for reference in all_references
    )
    metric_map = {item.reference: item for item in metrics}
    evidence_list: list[EvidenceMinimumOutcome] = []
    for minimum in validated_spec.evidence_minimums:
        metric_record = metric_map[minimum.metric]
        value = metric_record.value
        available = metric_record.availability is MetricAvailability.AVAILABLE and value is not None
        evidence_list.append(
            EvidenceMinimumOutcome(
                minimum,
                int(value) if available and value is not None else None,
                available and value is not None and value >= Decimal(minimum.minimum),
                None if available else metric_record.reason,
            )
        )
    evidence_outcomes = tuple(evidence_list)
    criteria_list: list[CriterionOutcome] = []
    for criterion in validated_spec.acceptance_criteria:
        metric_record = metric_map[criterion.metric]
        value = metric_record.value
        available = metric_record.availability is MetricAvailability.AVAILABLE and value is not None
        criteria_list.append(
            CriterionOutcome(
                criterion,
                value,
                available
                and value is not None
                and _compare(value, criterion.operator, criterion.threshold),
                None if available else metric_record.reason,
            )
        )
    criteria_outcomes = tuple(criteria_list)
    unavailable_required = tuple(
        item
        for item in validated_spec.required_metrics
        if metric_map[item].availability is not MetricAvailability.AVAILABLE
    )
    unsupported_criteria = tuple(
        item
        for item in validated_spec.acceptance_criteria
        if item.metric.metric in UNSUPPORTED_METRICS
        or metric_map[item.metric].availability is not MetricAvailability.AVAILABLE
        or metric_map[item.metric].value is None
    )

    result_reasons: list[ValidationReason] = []
    if fatal_reasons:
        status = StrategyValidationStatus.UNAVAILABLE
        result_reasons.extend(fatal_reasons)
    elif unavailable_required:
        status = StrategyValidationStatus.UNAVAILABLE
        result_reasons.append(
            ValidationReason(
                ValidationReasonCode.UNSUPPORTED_REQUIRED_METRIC,
                "one or more required metrics are unavailable under Milestone 4 authority",
            )
        )
    elif unsupported_criteria:
        status = StrategyValidationStatus.UNAVAILABLE
        result_reasons.append(
            ValidationReason(
                ValidationReasonCode.UNSUPPORTED_CRITERION_METRIC,
                "an acceptance criterion targets an unavailable metric",
            )
        )
    elif any(not item.met for item in evidence_outcomes):
        status = StrategyValidationStatus.INSUFFICIENT_EVIDENCE
        result_reasons.append(
            ValidationReason(
                ValidationReasonCode.EVIDENCE_MINIMUM_NOT_MET,
                "the valid complete schedule does not satisfy every evidence minimum",
            )
        )
    elif any(not item.met for item in criteria_outcomes):
        status = StrategyValidationStatus.CRITERIA_NOT_MET
        result_reasons.append(
            ValidationReason(
                ValidationReasonCode.ACCEPTANCE_CRITERION_NOT_MET,
                "adequate evidence does not satisfy every caller-supplied criterion",
            )
        )
    else:
        status = StrategyValidationStatus.VALIDATED
    result = _make_result(
        status=status,
        specification=validated_spec,
        records=immutable_records,
        status_metrics=status_metrics,
        reason_metrics=reason_metrics,
        frequency=frequency,
        persistence=persistence,
        strata=strata,
        metric_records=metrics,
        evidence=evidence_outcomes,
        criteria=criteria_outcomes,
        reasons=tuple(result_reasons),
    )
    historical_record = (
        SuccessfulHistoricalValidationRecord._from_evaluator(
            result, token=_HISTORICAL_RECORD_TRUST_TOKEN
        )
        if status is StrategyValidationStatus.VALIDATED
        else None
    )
    return StrategyValidationEvaluation(result, historical_record)


evaluate_strategy = evaluate_strategy_validation
validate_strategy = evaluate_strategy_validation

__all__ = ["evaluate_strategy", "evaluate_strategy_validation", "validate_strategy"]
