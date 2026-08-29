"""Immutable records for deterministic historical strategy validation.

These records are local historical diagnostics.  They are not executable,
simulated, risk-authorized, or trade-authorized artifacts.
"""

from __future__ import annotations

import hashlib
import weakref
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import SupportsIndex, cast

from invariant_engine.constraints import TrustedCompiledPricingConstraint
from invariant_engine.domain.decimal_policy import parse_decimal, parse_quantity
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference
from invariant_engine.opportunities import (
    FeePolicyAssignment,
    OpportunityEconomicsResult,
    OpportunityEconomicsStatus,
)
from invariant_engine.relationships import RelationshipCertificate, RelationshipType
from invariant_engine.relationships.ids import ClaimBindingId
from invariant_engine.serialization import stable_json_bytes

STRATEGY_VALIDATION_SCHEMA_VERSION = "strategy-validation-v1"
HISTORICAL_VALIDATION_RECORD_SCHEMA_VERSION = "historical-validation-record-v1"

_ROUNDING_MODES = frozenset(
    {
        "ROUND_CEILING",
        "ROUND_DOWN",
        "ROUND_FLOOR",
        "ROUND_HALF_DOWN",
        "ROUND_HALF_EVEN",
        "ROUND_HALF_UP",
        "ROUND_UP",
        "ROUND_05UP",
    }
)


def _aware(value: object, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f"{field} must be a timezone-aware datetime")
    return value


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} must be a non-empty string")
    return value


def _exact_tuple(value: object, field: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise DomainError(f"{field} must be an immutable tuple")
    return value


def _raw_refs(value: object, field: str, *, allow_empty: bool = False) -> tuple[RawReference, ...]:
    items = _exact_tuple(value, field)
    if (not items and not allow_empty) or any(type(item) is not RawReference for item in items):
        raise DomainError(f"{field} must contain exact RawReference values")
    result = tuple(item for item in items if isinstance(item, RawReference))
    if len(set(result)) != len(result):
        raise DomainError(f"{field} must not contain duplicates")
    return result


class StrategyValidationStatus(StrEnum):
    VALIDATED = "validated"
    CRITERIA_NOT_MET = "criteria_not_met"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNAVAILABLE = "unavailable"


class Eligibility(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"


class EligibilityRuleKind(StrEnum):
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


class DenominatorSemantics(StrEnum):
    ALL_SCHEDULED_OBSERVATIONS = "all_scheduled_observations"


class GapTreatment(StrEnum):
    RETAIN_AS_UNAVAILABLE_AND_BREAK_PERSISTENCE = "retain_as_unavailable_and_break_persistence"


class PartitionPurpose(StrEnum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"
    TEST = "test"
    HISTORICAL_ANALYSIS = "historical_analysis"


class MetricName(StrEnum):
    SCHEDULED_COUNT = "scheduled_count"
    ELIGIBLE_COUNT = "eligible_count"
    INELIGIBLE_COUNT = "ineligible_count"
    STATUS_COUNT = "status_count"
    STATUS_RATE = "status_rate"
    REASON_COUNT = "reason_count"
    REASON_RATE = "reason_rate"
    VALIDATED_OPPORTUNITY_FREQUENCY = "validated_opportunity_frequency"
    MAX_PERSISTENCE_OBSERVATIONS = "max_persistence_observations"
    REQUESTED_QUANTITY = "requested_quantity"
    OBSERVED_DEPTH_DIAGNOSTICS = "observed_depth_diagnostics"
    PURCHASE_COST = "purchase_cost"
    FEE_INTERVAL = "fee_interval"
    GROSS_EDGE_INTERVAL = "gross_edge_interval"
    NET_EDGE_INTERVAL = "net_edge_interval"
    RESIDUAL_SINGLE_LEG_FAILURE_RANGES = "residual_single_leg_failure_ranges"
    DATA_QUALITY_FAILURE_COUNT = "data_quality_failure_count"
    LATENCY = "latency"
    QUEUE_POSITION = "queue_position"
    FILL_PROBABILITY = "fill_probability"
    PARTIAL_FILLS = "partial_fills"
    CANCELLATION = "cancellation"
    EXECUTION_SEQUENCING = "execution_sequencing"
    FALSE_RELATIONSHIP_GROUND_TRUTH = "false_relationship_ground_truth"
    PORTFOLIO_CAPITAL_ALLOCATION = "portfolio_capital_allocation"
    CONCURRENT_CAPITAL_USAGE = "concurrent_capital_usage"
    REALIZED_PORTFOLIO_PNL = "realized_portfolio_pnl"
    DRAWDOWNS = "drawdowns"


UNSUPPORTED_METRICS = (
    MetricName.LATENCY,
    MetricName.QUEUE_POSITION,
    MetricName.FILL_PROBABILITY,
    MetricName.PARTIAL_FILLS,
    MetricName.CANCELLATION,
    MetricName.EXECUTION_SEQUENCING,
    MetricName.FALSE_RELATIONSHIP_GROUND_TRUTH,
    MetricName.PORTFOLIO_CAPITAL_ALLOCATION,
    MetricName.CONCURRENT_CAPITAL_USAGE,
    MetricName.REALIZED_PORTFOLIO_PNL,
    MetricName.DRAWDOWNS,
)


class ComparisonOperator(StrEnum):
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "="
    GREATER_THAN_OR_EQUAL = ">="
    GREATER_THAN = ">"


class MetricAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_EVALUATED = "not_evaluated"


class UnavailabilityCode(StrEnum):
    EXPLICIT_SCHEDULE_GAP = "explicit_schedule_gap"
    HISTORICAL_INPUT_UNAVAILABLE = "historical_input_unavailable"
    DATA_QUALITY_FAILURE = "data_quality_failure"
    GOVERNED_EXCLUSION = "governed_exclusion"


class ValidationReasonCode(StrEnum):
    INVALID_SPECIFICATION = "invalid_specification"
    INVALID_RUNTIME_SLOT = "invalid_runtime_slot"
    SCHEDULE_MISMATCH = "schedule_mismatch"
    DUPLICATE_OBSERVATION_ID = "duplicate_observation_id"
    DUPLICATE_MATERIAL = "duplicate_material"
    CROSS_PARTITION_MATERIAL_REUSE = "cross_partition_material_reuse"
    INVALID_PARTITION = "invalid_partition"
    TEMPORAL_LEAKAGE = "temporal_leakage"
    QUANTITY_MISMATCH = "quantity_mismatch"
    RELATIONSHIP_CLASS_MISMATCH = "relationship_class_mismatch"
    UNTRUSTED_UPSTREAM = "untrusted_upstream"
    UNSUPPORTED_REQUIRED_METRIC = "unsupported_required_metric"
    UNSUPPORTED_CRITERION_METRIC = "unsupported_criterion_metric"
    EVIDENCE_MINIMUM_NOT_MET = "evidence_minimum_not_met"
    ACCEPTANCE_CRITERION_NOT_MET = "acceptance_criterion_not_met"
    EXPLICIT_UNAVAILABLE_SLOT = "explicit_unavailable_slot"


@dataclass(frozen=True, slots=True)
class EligibilityRule:
    rule_id: str
    kind: EligibilityRuleKind
    description: str

    def __post_init__(self) -> None:
        _nonempty(self.rule_id, "eligibility rule ID")
        if not isinstance(self.kind, EligibilityRuleKind):
            raise DomainError("eligibility rule kind is invalid")
        _nonempty(self.description, "eligibility rule description")


@dataclass(frozen=True, slots=True)
class ScheduledObservation:
    observation_id: str
    timestamp: datetime
    relationship_class: RelationshipType
    quantity: Decimal
    grouping_identity: str
    strata: tuple[tuple[str, str], ...]
    eligibility: Eligibility
    applied_rule_ids: tuple[str, ...]
    partition_id: str | None

    def __post_init__(self) -> None:
        _nonempty(self.observation_id, "scheduled observation ID")
        _aware(self.timestamp, "scheduled timestamp")
        if not isinstance(self.relationship_class, RelationshipType):
            raise DomainError("scheduled relationship class is invalid")
        quantity = parse_quantity(self.quantity, field="scheduled quantity")
        if type(self.quantity) is not Decimal or quantity <= 0:
            raise DomainError("scheduled quantity must be an exact positive Decimal")
        object.__setattr__(self, "quantity", quantity)
        _nonempty(self.grouping_identity, "grouping identity")
        strata = _exact_tuple(self.strata, "scheduled strata")
        normalized: list[tuple[str, str]] = []
        for item in strata:
            if type(item) is not tuple or len(item) != 2:
                raise DomainError("scheduled strata must contain immutable key/value pairs")
            key, value = item
            normalized.append((_nonempty(key, "stratum key"), _nonempty(value, "stratum value")))
        if len({key for key, _ in normalized}) != len(normalized):
            raise DomainError("scheduled stratum keys must be unique")
        object.__setattr__(self, "strata", tuple(normalized))
        if not isinstance(self.eligibility, Eligibility):
            raise DomainError("scheduled eligibility is invalid")
        rule_ids = _exact_tuple(self.applied_rule_ids, "applied rule IDs")
        if not rule_ids or any(not isinstance(item, str) or not item.strip() for item in rule_ids):
            raise DomainError("each scheduled observation must bind explicit rule IDs")
        if len(set(rule_ids)) != len(rule_ids):
            raise DomainError("applied rule IDs must be unique")
        if self.partition_id is not None:
            _nonempty(self.partition_id, "partition ID")


@dataclass(frozen=True, slots=True)
class ChronologicalPartition:
    partition_id: str
    purpose: PartitionPurpose
    start: datetime
    end: datetime
    start_inclusive: bool
    end_inclusive: bool
    observation_ids: tuple[str, ...]
    provenance: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        _nonempty(self.partition_id, "partition ID")
        if not isinstance(self.purpose, PartitionPurpose):
            raise DomainError("partition purpose is invalid")
        start = _aware(self.start, "partition start")
        end = _aware(self.end, "partition end")
        if start.astimezone(UTC) > end.astimezone(UTC):
            raise DomainError("partition interval is inverted")
        if type(self.start_inclusive) is not bool or type(self.end_inclusive) is not bool:
            raise DomainError("partition boundary inclusion must be explicit booleans")
        values = _exact_tuple(self.observation_ids, "partition observation IDs")
        if not values or any(not isinstance(item, str) or not item.strip() for item in values):
            raise DomainError("partition observation IDs must be non-empty strings")
        if len(set(values)) != len(values):
            raise DomainError("partition observation IDs must be unique")
        object.__setattr__(self, "provenance", _raw_refs(self.provenance, "partition provenance"))

    def contains(self, timestamp: datetime) -> bool:
        instant = _aware(timestamp, "partition comparison timestamp").astimezone(UTC)
        start = self.start.astimezone(UTC)
        end = self.end.astimezone(UTC)
        return (instant > start or (self.start_inclusive and instant == start)) and (
            instant < end or (self.end_inclusive and instant == end)
        )


@dataclass(frozen=True, slots=True)
class MetricReference:
    metric: MetricName
    status: OpportunityEconomicsStatus | None
    reason_code: str | None
    scope: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricName):
            raise DomainError("metric reference metric is invalid")
        if self.status is not None and not isinstance(self.status, OpportunityEconomicsStatus):
            raise DomainError("metric status selector is invalid")
        if self.reason_code is not None:
            _nonempty(self.reason_code, "metric reason selector")
        raw_scope = _exact_tuple(self.scope, "metric scope")
        for item in raw_scope:
            if type(item) is not tuple or len(item) != 2:
                raise DomainError("metric scope must contain immutable key/value pairs")
            pair = cast(tuple[object, object], item)
            _nonempty(pair[0], "metric scope key")
            _nonempty(pair[1], "metric scope value")
        scope = cast(tuple[tuple[str, str], ...], raw_scope)
        keys = tuple(item[0] for item in scope)
        if len(set(keys)) != len(keys):
            raise DomainError("metric scope keys must be unique")
        if self.metric in (MetricName.STATUS_COUNT, MetricName.STATUS_RATE) and self.status is None:
            raise DomainError("status metrics require an explicit status selector")
        if (
            self.metric in (MetricName.REASON_COUNT, MetricName.REASON_RATE)
            and self.reason_code is None
        ):
            raise DomainError("reason metrics require an explicit reason selector")
        if (
            self.metric not in (MetricName.STATUS_COUNT, MetricName.STATUS_RATE)
            and self.status is not None
        ):
            raise DomainError("status selector is only valid for status metrics")
        if (
            self.metric not in (MetricName.REASON_COUNT, MetricName.REASON_RATE)
            and self.reason_code is not None
        ):
            raise DomainError("reason selector is only valid for reason metrics")


@dataclass(frozen=True, slots=True)
class EvidenceMinimum:
    minimum_id: str
    metric: MetricReference
    minimum: int

    def __post_init__(self) -> None:
        _nonempty(self.minimum_id, "evidence minimum ID")
        if type(self.metric) is not MetricReference:
            raise DomainError("evidence minimum requires an exact MetricReference")
        if type(self.minimum) is not int or self.minimum < 0:
            raise DomainError("evidence minimum must be a non-negative integer")
        if self.metric.metric not in {
            MetricName.SCHEDULED_COUNT,
            MetricName.ELIGIBLE_COUNT,
            MetricName.INELIGIBLE_COUNT,
            MetricName.STATUS_COUNT,
            MetricName.REASON_COUNT,
            MetricName.MAX_PERSISTENCE_OBSERVATIONS,
        }:
            raise DomainError("evidence minimum must target an integer metric")


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    criterion_id: str
    metric: MetricReference
    operator: ComparisonOperator
    threshold: Decimal

    def __post_init__(self) -> None:
        _nonempty(self.criterion_id, "acceptance criterion ID")
        if type(self.metric) is not MetricReference:
            raise DomainError("acceptance criterion requires an exact MetricReference")
        if not isinstance(self.operator, ComparisonOperator):
            raise DomainError("acceptance criterion comparator is invalid")
        threshold = parse_decimal(self.threshold, field="acceptance threshold")
        if type(self.threshold) is not Decimal:
            raise DomainError("acceptance threshold must be an exact Decimal")
        object.__setattr__(self, "threshold", threshold)


@dataclass(frozen=True, slots=True)
class StrategyValidationSpecification:
    schema_version: str
    strategy_id: str
    strategy_version: str
    analysis_start: datetime
    analysis_end: datetime
    start_inclusive: bool
    end_inclusive: bool
    included_relationship_classes: tuple[RelationshipType, ...]
    schedule: tuple[ScheduledObservation, ...]
    sampling_semantics: str
    grouping_key: str
    grouping_semantics: str
    stratification_keys: tuple[str, ...]
    inclusion_rules: tuple[EligibilityRule, ...]
    exclusion_rules: tuple[EligibilityRule, ...]
    denominator_semantics: DenominatorSemantics
    gap_treatment: GapTreatment
    partitions: tuple[ChronologicalPartition, ...]
    required_metrics: tuple[MetricReference, ...]
    evidence_minimums: tuple[EvidenceMinimum, ...]
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    ratio_precision: int
    rounding_mode: str
    provenance: tuple[RawReference, ...]
    specification_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != STRATEGY_VALIDATION_SCHEMA_VERSION:
            raise DomainError("unsupported strategy-validation schema version")
        _nonempty(self.strategy_id, "strategy ID")
        _nonempty(self.strategy_version, "strategy version")
        start = _aware(self.analysis_start, "analysis start")
        end = _aware(self.analysis_end, "analysis end")
        if start.astimezone(UTC) > end.astimezone(UTC):
            raise DomainError("historical analysis interval is inverted")
        if type(self.start_inclusive) is not bool or type(self.end_inclusive) is not bool:
            raise DomainError("analysis boundary inclusion must be explicit booleans")
        raw_relationships = _exact_tuple(
            self.included_relationship_classes, "included relationship classes"
        )
        if not raw_relationships or any(
            not isinstance(item, RelationshipType) for item in raw_relationships
        ):
            raise DomainError("included relationship classes must be explicit and non-empty")
        relationships = cast(tuple[RelationshipType, ...], raw_relationships)
        if len(set(relationships)) != len(relationships):
            raise DomainError("included relationship classes must be unique")
        raw_schedule = _exact_tuple(self.schedule, "observation schedule")
        if not raw_schedule or any(type(item) is not ScheduledObservation for item in raw_schedule):
            raise DomainError("observation schedule must contain exact ScheduledObservation values")
        schedule = cast(tuple[ScheduledObservation, ...], raw_schedule)
        observation_ids = tuple(item.observation_id for item in schedule)
        if len(set(observation_ids)) != len(observation_ids):
            raise DomainError("observation schedule IDs must be unique")
        timestamps = tuple(item.timestamp.astimezone(UTC) for item in schedule)
        if timestamps != tuple(sorted(timestamps)):
            raise DomainError("observation schedule must be chronological")
        for item in schedule:
            instant = item.timestamp.astimezone(UTC)
            in_interval = (
                instant > start.astimezone(UTC)
                or (self.start_inclusive and instant == start.astimezone(UTC))
            ) and (
                instant < end.astimezone(UTC)
                or (self.end_inclusive and instant == end.astimezone(UTC))
            )
            if not in_interval:
                raise DomainError("scheduled timestamp lies outside the analysis interval")
            if item.relationship_class not in relationships:
                raise DomainError("scheduled relationship class is not included")
        _nonempty(self.sampling_semantics, "sampling semantics")
        _nonempty(self.grouping_key, "grouping key")
        _nonempty(self.grouping_semantics, "grouping semantics")
        stratum_keys = _exact_tuple(self.stratification_keys, "stratification keys")
        if any(not isinstance(item, str) or not item.strip() for item in stratum_keys):
            raise DomainError("stratification keys must be non-empty strings")
        if len(set(stratum_keys)) != len(stratum_keys):
            raise DomainError("stratification keys must be unique")
        if any(tuple(key for key, _ in item.strata) != stratum_keys for item in schedule):
            raise DomainError("every schedule slot must bind every stratum in declared order")
        raw_inclusion = _exact_tuple(self.inclusion_rules, "inclusion rules")
        raw_exclusion = _exact_tuple(self.exclusion_rules, "exclusion rules")
        if not raw_inclusion or any(
            type(item) is not EligibilityRule or item.kind is not EligibilityRuleKind.INCLUSION
            for item in raw_inclusion
        ):
            raise DomainError("at least one exact inclusion rule is required")
        if any(
            type(item) is not EligibilityRule or item.kind is not EligibilityRuleKind.EXCLUSION
            for item in raw_exclusion
        ):
            raise DomainError("exclusion rules must be exact exclusion EligibilityRule values")
        inclusion = cast(tuple[EligibilityRule, ...], raw_inclusion)
        exclusion = cast(tuple[EligibilityRule, ...], raw_exclusion)
        all_rules = tuple(item.rule_id for item in (*inclusion, *exclusion))
        if len(set(all_rules)) != len(all_rules):
            raise DomainError("eligibility rule IDs must be unique")
        rule_kind = {item.rule_id: item.kind for item in (*inclusion, *exclusion)}
        for item in schedule:
            if any(rule_id not in rule_kind for rule_id in item.applied_rule_ids):
                raise DomainError("schedule slot references an unknown eligibility rule")
            expected_kind = (
                EligibilityRuleKind.INCLUSION
                if item.eligibility is Eligibility.INCLUDED
                else EligibilityRuleKind.EXCLUSION
            )
            if any(rule_kind[rule_id] is not expected_kind for rule_id in item.applied_rule_ids):
                raise DomainError("schedule eligibility and applied rule kind disagree")
        if self.denominator_semantics is not DenominatorSemantics.ALL_SCHEDULED_OBSERVATIONS:
            raise DomainError("unsupported denominator semantics")
        if self.gap_treatment is not GapTreatment.RETAIN_AS_UNAVAILABLE_AND_BREAK_PERSISTENCE:
            raise DomainError("unsupported schedule-gap treatment")
        raw_partitions = _exact_tuple(self.partitions, "chronological partitions")
        if any(type(item) is not ChronologicalPartition for item in raw_partitions):
            raise DomainError("partitions must contain exact ChronologicalPartition values")
        partitions = cast(tuple[ChronologicalPartition, ...], raw_partitions)
        if len({item.partition_id for item in partitions}) != len(partitions):
            raise DomainError("partition IDs must be unique")
        if partitions:
            ordered = tuple(item.start.astimezone(UTC) for item in partitions)
            if ordered != tuple(sorted(ordered)):
                raise DomainError("partitions must be chronological")
            for previous, current in zip(partitions, partitions[1:], strict=False):
                previous_end = previous.end.astimezone(UTC)
                current_start = current.start.astimezone(UTC)
                if previous_end > current_start or (
                    previous_end == current_start
                    and previous.end_inclusive
                    and current.start_inclusive
                ):
                    raise DomainError("chronological partitions must not overlap")
            partition_map = {item.partition_id: item for item in partitions}
            seen: list[str] = []
            for partition in partitions:
                expected_members = tuple(
                    item.observation_id
                    for item in schedule
                    if item.partition_id == partition.partition_id
                )
                if partition.observation_ids != expected_members:
                    raise DomainError("partition membership must exactly match schedule order")
                for observation_id in partition.observation_ids:
                    scheduled = schedule[observation_ids.index(observation_id)]
                    if not partition.contains(scheduled.timestamp):
                        raise DomainError("partition membership creates temporal leakage")
                seen.extend(partition.observation_ids)
            if tuple(seen) != observation_ids:
                raise DomainError("partitions must cover the complete schedule exactly once")
            if any(item.partition_id not in partition_map for item in schedule):
                raise DomainError("schedule slot references an unknown partition")
        elif any(item.partition_id is not None for item in schedule):
            raise DomainError("schedule partition IDs require explicit partitions")
        raw_required = _exact_tuple(self.required_metrics, "required metrics")
        raw_minimums = _exact_tuple(self.evidence_minimums, "evidence minimums")
        raw_criteria = _exact_tuple(self.acceptance_criteria, "acceptance criteria")
        if not raw_required:
            raise DomainError("required metrics must be non-empty")
        if not raw_minimums:
            raise DomainError("evidence minimums must be non-empty")
        if not raw_criteria:
            raise DomainError("acceptance criteria must be non-empty")
        if any(type(item) is not MetricReference for item in raw_required):
            raise DomainError("required metrics must contain exact MetricReference values")
        if any(type(item) is not EvidenceMinimum for item in raw_minimums):
            raise DomainError("evidence minimums must contain exact EvidenceMinimum values")
        if any(type(item) is not AcceptanceCriterion for item in raw_criteria):
            raise DomainError("acceptance criteria must contain exact AcceptanceCriterion values")
        required = cast(tuple[MetricReference, ...], raw_required)
        minimums = cast(tuple[EvidenceMinimum, ...], raw_minimums)
        criteria = cast(tuple[AcceptanceCriterion, ...], raw_criteria)
        if len(set(required)) != len(required):
            raise DomainError("required metric references must be unique")
        if len({item.minimum_id for item in minimums}) != len(minimums):
            raise DomainError("evidence minimum IDs must be unique")
        if len({item.criterion_id for item in criteria}) != len(criteria):
            raise DomainError("acceptance criterion IDs must be unique")
        if type(self.ratio_precision) is not int or self.ratio_precision <= 0:
            raise DomainError("ratio precision must be an explicit positive integer")
        if self.rounding_mode not in _ROUNDING_MODES:
            raise DomainError("ratio rounding mode is unsupported")
        object.__setattr__(
            self, "provenance", _raw_refs(self.provenance, "specification provenance")
        )
        identity_content = {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "analysis_start": self.analysis_start,
            "analysis_end": self.analysis_end,
            "start_inclusive": self.start_inclusive,
            "end_inclusive": self.end_inclusive,
            "included_relationship_classes": self.included_relationship_classes,
            "schedule": self.schedule,
            "sampling_semantics": self.sampling_semantics,
            "grouping_key": self.grouping_key,
            "grouping_semantics": self.grouping_semantics,
            "stratification_keys": self.stratification_keys,
            "inclusion_rules": self.inclusion_rules,
            "exclusion_rules": self.exclusion_rules,
            "denominator_semantics": self.denominator_semantics,
            "gap_treatment": self.gap_treatment,
            "partitions": self.partitions,
            "required_metrics": self.required_metrics,
            "evidence_minimums": self.evidence_minimums,
            "acceptance_criteria": self.acceptance_criteria,
            "ratio_precision": self.ratio_precision,
            "rounding_mode": self.rounding_mode,
            "provenance": self.provenance,
        }
        digest = hashlib.sha256(stable_json_bytes(identity_content)).hexdigest()
        object.__setattr__(self, "specification_id", "strategy-specification:" + digest)


@dataclass(frozen=True, slots=True)
class CompleteObservationSlot:
    observation_id: str
    timestamp: datetime
    certificate: RelationshipCertificate
    constraint: TrustedCompiledPricingConstraint
    snapshots: tuple[tuple[ClaimBindingId, object], ...]
    quantity: Decimal
    fee_policies: tuple[FeePolicyAssignment, ...]
    provenance: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        _nonempty(self.observation_id, "runtime observation ID")
        _aware(self.timestamp, "runtime observation timestamp")
        if type(self.certificate) is not RelationshipCertificate:
            raise DomainError("complete slot requires an exact RelationshipCertificate")
        if type(self.constraint) is not TrustedCompiledPricingConstraint:
            raise DomainError("complete slot requires an exact compiler constraint")
        raw_snapshots = _exact_tuple(self.snapshots, "runtime snapshots")
        keys: list[ClaimBindingId] = []
        for item in raw_snapshots:
            if type(item) is not tuple or len(item) != 2 or type(item[0]) is not ClaimBindingId:
                raise DomainError("runtime snapshots must be immutable binding/snapshot pairs")
            keys.append(cast(tuple[ClaimBindingId, object], item)[0])
        snapshots = cast(tuple[tuple[ClaimBindingId, object], ...], raw_snapshots)
        if not snapshots or len(set(keys)) != len(keys):
            raise DomainError("runtime snapshots must be non-empty with unique bindings")
        quantity = parse_quantity(self.quantity, field="runtime quantity")
        if type(self.quantity) is not Decimal or quantity <= 0:
            raise DomainError("runtime quantity must be an exact positive Decimal")
        object.__setattr__(self, "quantity", quantity)
        raw_policies = _exact_tuple(self.fee_policies, "runtime fee policies")
        if not raw_policies or any(type(item) is not FeePolicyAssignment for item in raw_policies):
            raise DomainError("runtime fee policies must contain exact assignments")
        policies = cast(tuple[FeePolicyAssignment, ...], raw_policies)
        if len({item.claim_binding_id for item in policies}) != len(policies):
            raise DomainError("runtime fee-policy assignments must be unique")
        object.__setattr__(self, "provenance", _raw_refs(self.provenance, "runtime provenance"))


@dataclass(frozen=True, slots=True)
class UnavailabilityReason:
    code: UnavailabilityCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, UnavailabilityCode):
            raise DomainError("unavailability code is invalid")
        _nonempty(self.message, "unavailability message")


@dataclass(frozen=True, slots=True)
class ExplicitUnavailableSlot:
    observation_id: str
    timestamp: datetime
    reason: UnavailabilityReason
    provenance: tuple[RawReference, ...]

    def __post_init__(self) -> None:
        _nonempty(self.observation_id, "unavailable observation ID")
        _aware(self.timestamp, "unavailable observation timestamp")
        if type(self.reason) is not UnavailabilityReason:
            raise DomainError("unavailable slot requires an exact structured reason")
        object.__setattr__(
            self, "provenance", _raw_refs(self.provenance, "unavailability provenance")
        )


RuntimeObservationSlot = CompleteObservationSlot | ExplicitUnavailableSlot


@dataclass(frozen=True, slots=True)
class ValidationReason:
    code: ValidationReasonCode
    message: str
    observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Ratio:
    numerator: int
    denominator: int
    decimal: Decimal | None


@dataclass(frozen=True, slots=True)
class StatusMetric:
    status: OpportunityEconomicsStatus
    count: int
    rate: Ratio


@dataclass(frozen=True, slots=True)
class ReasonMetric:
    reason_code: str
    count: int
    rate: Ratio


@dataclass(frozen=True, slots=True)
class PersistenceRun:
    grouping_identity: str
    observation_ids: tuple[str, ...]
    start_timestamp: datetime
    end_timestamp: datetime
    observation_count: int
    observed_duration: Decimal


@dataclass(frozen=True, slots=True)
class ObservationValidationRecord:
    scheduled: ScheduledObservation
    supplied_slot: RuntimeObservationSlot
    material_fingerprint: str | None
    economics_result: OpportunityEconomicsResult | None
    effective_status: OpportunityEconomicsStatus
    provenance: tuple[RawReference, ...]


@dataclass(frozen=True, slots=True)
class StratumResult:
    scope: tuple[tuple[str, str], ...]
    scheduled_count: int
    eligible_count: int
    ineligible_count: int
    status_metrics: tuple[StatusMetric, ...]
    reason_metrics: tuple[ReasonMetric, ...]
    validated_opportunity_frequency: Ratio


@dataclass(frozen=True, slots=True)
class MetricRecord:
    reference: MetricReference
    availability: MetricAvailability
    value: Decimal | None
    numerator: int | None
    denominator: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class EvidenceMinimumOutcome:
    minimum: EvidenceMinimum
    actual: int | None
    met: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class CriterionOutcome:
    criterion: AcceptanceCriterion
    actual: Decimal | None
    met: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class UnsupportedMetricRecord:
    metric: MetricName
    availability: MetricAvailability
    reason: str
    numeric_value: None = None


@dataclass(frozen=True, slots=True)
class StrategyValidationResult:
    schema_version: str
    validation_id: str
    dataset_id: str
    status: StrategyValidationStatus
    specification: StrategyValidationSpecification | None
    observation_records: tuple[ObservationValidationRecord, ...]
    scheduled_count: int
    eligible_count: int
    ineligible_count: int
    status_metrics: tuple[StatusMetric, ...]
    reason_metrics: tuple[ReasonMetric, ...]
    validated_opportunity_frequency: Ratio
    persistence_runs: tuple[PersistenceRun, ...]
    strata: tuple[StratumResult, ...]
    metric_records: tuple[MetricRecord, ...]
    evidence_outcomes: tuple[EvidenceMinimumOutcome, ...]
    criterion_outcomes: tuple[CriterionOutcome, ...]
    unsupported_metrics: tuple[UnsupportedMetricRecord, ...]
    reasons: tuple[ValidationReason, ...]
    provenance: tuple[RawReference, ...]
    historical: bool
    non_actionable: bool
    future_profit_claim: bool
    execution_supported: bool
    simulation_supported: bool
    risk_authorized: bool
    trade_authorized: bool


_HISTORICAL_RECORD_TRUST_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _HistoricalTrustEntry:
    reference: weakref.ReferenceType[object]
    commitment: str


_TRUSTED_HISTORICAL_RECORDS: dict[int, _HistoricalTrustEntry] = {}


def _remove_historical_trust(key: int, reference: weakref.ReferenceType[object]) -> None:
    entry = _TRUSTED_HISTORICAL_RECORDS.get(key)
    if entry is not None and entry.reference is reference:
        _TRUSTED_HISTORICAL_RECORDS.pop(key, None)


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class SuccessfulHistoricalValidationRecord:
    """Evaluator-produced, historical, explicitly non-actionable success record."""

    schema_version: str
    record_id: str
    validation_result: StrategyValidationResult
    historical: bool
    non_actionable: bool
    statement: str
    future_profit_claim: bool
    execution_supported: bool
    simulation_supported: bool
    risk_authorized: bool
    trade_authorized: bool

    @classmethod
    def _from_evaluator(
        cls, result: StrategyValidationResult, *, token: object
    ) -> SuccessfulHistoricalValidationRecord:
        if token is not _HISTORICAL_RECORD_TRUST_TOKEN:
            raise DomainError("historical record trust may only be issued by the evaluator")
        if result.status is not StrategyValidationStatus.VALIDATED:
            raise DomainError("only a validated strategy result may produce a historical record")
        content = {
            "schema_version": HISTORICAL_VALIDATION_RECORD_SCHEMA_VERSION,
            "validation_result": result,
            "historical": True,
            "non_actionable": True,
            "statement": (
                "Historical validation only; not actionable and not evidence of future "
                "profitability, executability, simulation support, risk authorization, or "
                "trade authorization."
            ),
            "future_profit_claim": False,
            "execution_supported": False,
            "simulation_supported": False,
            "risk_authorized": False,
            "trade_authorized": False,
        }
        digest = hashlib.sha256(stable_json_bytes(content)).hexdigest()
        record = object.__new__(cls)
        object.__setattr__(record, "schema_version", HISTORICAL_VALIDATION_RECORD_SCHEMA_VERSION)
        object.__setattr__(record, "record_id", "historical-validation-record:" + digest)
        for key, value in content.items():
            if key != "schema_version":
                object.__setattr__(record, key, value)
        identity = id(record)

        def cleanup(reference: weakref.ReferenceType[object]) -> None:
            _remove_historical_trust(identity, reference)

        _TRUSTED_HISTORICAL_RECORDS[identity] = _HistoricalTrustEntry(
            weakref.ref(record, cleanup), digest
        )
        return record

    def __deepcopy__(self, memo: dict[int, object]) -> SuccessfulHistoricalValidationRecord:
        clone = object.__new__(type(self))
        memo[id(self)] = clone
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
            object.__setattr__(clone, name, getattr(self, name))
        return clone

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[object, tuple[object, ...]]:
        del protocol
        return (_reconstruct_untrusted_historical_record, (self.schema_version, self.record_id))


def _reconstruct_untrusted_historical_record(
    schema_version: str, record_id: str
) -> SuccessfulHistoricalValidationRecord:
    record = object.__new__(SuccessfulHistoricalValidationRecord)
    object.__setattr__(record, "schema_version", schema_version)
    object.__setattr__(record, "record_id", record_id)
    object.__setattr__(record, "validation_result", None)
    object.__setattr__(record, "historical", True)
    object.__setattr__(record, "non_actionable", True)
    object.__setattr__(record, "statement", "Untrusted serialized historical data.")
    object.__setattr__(record, "future_profit_claim", False)
    object.__setattr__(record, "execution_supported", False)
    object.__setattr__(record, "simulation_supported", False)
    object.__setattr__(record, "risk_authorized", False)
    object.__setattr__(record, "trade_authorized", False)
    return record


def historical_record_identity_content(
    record: SuccessfulHistoricalValidationRecord,
) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "validation_result": record.validation_result,
        "historical": record.historical,
        "non_actionable": record.non_actionable,
        "statement": record.statement,
        "future_profit_claim": record.future_profit_claim,
        "execution_supported": record.execution_supported,
        "simulation_supported": record.simulation_supported,
        "risk_authorized": record.risk_authorized,
        "trade_authorized": record.trade_authorized,
    }


def is_trusted_historical_validation_record(value: object) -> bool:
    if type(value) is not SuccessfulHistoricalValidationRecord:
        return False
    entry = _TRUSTED_HISTORICAL_RECORDS.get(id(value))
    if entry is None or entry.reference() is not value:
        return False
    try:
        digest = hashlib.sha256(
            stable_json_bytes(historical_record_identity_content(value))
        ).hexdigest()
        return (
            digest == entry.commitment
            and value.schema_version == HISTORICAL_VALIDATION_RECORD_SCHEMA_VERSION
            and value.record_id == "historical-validation-record:" + digest
            and value.validation_result.status is StrategyValidationStatus.VALIDATED
            and value.historical is True
            and value.non_actionable is True
            and value.future_profit_claim is False
            and value.execution_supported is False
            and value.simulation_supported is False
            and value.risk_authorized is False
            and value.trade_authorized is False
        )
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class StrategyValidationEvaluation:
    result: StrategyValidationResult
    historical_record: SuccessfulHistoricalValidationRecord | None

    @property
    def status(self) -> StrategyValidationStatus:
        return self.result.status

    @property
    def record(self) -> SuccessfulHistoricalValidationRecord | None:
        return self.historical_record


__all__ = [
    "AcceptanceCriterion",
    "ChronologicalPartition",
    "ComparisonOperator",
    "CompleteObservationSlot",
    "CriterionOutcome",
    "DenominatorSemantics",
    "Eligibility",
    "EligibilityRule",
    "EligibilityRuleKind",
    "EvidenceMinimum",
    "EvidenceMinimumOutcome",
    "ExplicitUnavailableSlot",
    "GapTreatment",
    "HISTORICAL_VALIDATION_RECORD_SCHEMA_VERSION",
    "MetricAvailability",
    "MetricName",
    "MetricRecord",
    "MetricReference",
    "ObservationValidationRecord",
    "PartitionPurpose",
    "PersistenceRun",
    "Ratio",
    "ReasonMetric",
    "RuntimeObservationSlot",
    "STRATEGY_VALIDATION_SCHEMA_VERSION",
    "ScheduledObservation",
    "StatusMetric",
    "StrategyValidationEvaluation",
    "StrategyValidationResult",
    "StrategyValidationSpecification",
    "StrategyValidationStatus",
    "StratumResult",
    "SuccessfulHistoricalValidationRecord",
    "UNSUPPORTED_METRICS",
    "UnavailabilityCode",
    "UnavailabilityReason",
    "UnsupportedMetricRecord",
    "ValidationReason",
    "ValidationReasonCode",
    "_HISTORICAL_RECORD_TRUST_TOKEN",
    "historical_record_identity_content",
    "is_trusted_historical_validation_record",
]
