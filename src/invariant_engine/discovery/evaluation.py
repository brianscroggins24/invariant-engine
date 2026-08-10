"""Deterministic measurements for recorded discovery experiments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invariant_engine.discovery.schema import DISCOVERY_EVALUATION_LABELS_VERSION
from invariant_engine.discovery.source import RecordedCost, RecordedLatency
from invariant_engine.domain.errors import DomainError


class EvaluationLabel(StrEnum):
    TP = "tp"
    FP = "fp"
    FN = "fn"
    TN = "tn"
    ABSTAIN = "abstain"


class ReviewerLabel(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    case_id: str
    label: EvaluationLabel
    malformed_attempts: int = 0
    recorded_attempts: int = 0
    repeat_group_id: str | None = None
    output_bytes: bytes | None = None
    reviewer_label: ReviewerLabel | None = None
    cost: RecordedCost = RecordedCost()
    latency: RecordedLatency = RecordedLatency()

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise DomainError("evaluation case_id must be non-empty")
        if not isinstance(self.label, EvaluationLabel):
            raise DomainError("evaluation label is unsupported")
        for field in ("malformed_attempts", "recorded_attempts"):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DomainError(f"{field} must be a non-negative integer")
        if self.malformed_attempts > self.recorded_attempts:
            raise DomainError("malformed attempts cannot exceed recorded attempts")
        if self.repeat_group_id is not None and not self.repeat_group_id.strip():
            raise DomainError("repeat_group_id must be non-empty when supplied")
        if not isinstance(self.cost, RecordedCost) or not isinstance(self.latency, RecordedLatency):
            raise DomainError("evaluation observations have invalid metadata")


@dataclass(frozen=True, slots=True)
class RepeatGroup:
    group_id: str
    output_bytes: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise DomainError("repeat group ID must be non-empty")
        if not isinstance(self.output_bytes, tuple):
            object.__setattr__(self, "output_bytes", tuple(self.output_bytes))
        if not self.output_bytes:
            raise DomainError("repeat group must contain outputs")
        if any(not isinstance(item, bytes) for item in self.output_bytes):
            raise DomainError("repeat group outputs must be bytes")


@dataclass(frozen=True, slots=True)
class CostMetric:
    unit: str
    currency: str
    observation_count: int
    total: Decimal
    mean: Decimal


@dataclass(frozen=True, slots=True)
class LatencyMetric:
    unit: str
    observation_count: int
    total: Decimal
    mean: Decimal


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    schema_version: str
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    abstention_count: int
    evaluated_case_count: int
    malformed_attempt_count: int
    recorded_attempt_count: int
    repeated_run_consistent_groups: int
    repeated_run_groups: int
    reviewer_accepted_count: int
    reviewer_reject_count: int
    precision: Decimal | None
    recall: Decimal | None
    false_positive_rate: Decimal | None
    abstention_rate: Decimal | None
    malformed_output_rate: Decimal | None
    repeated_run_consistency: Decimal | None
    reviewer_acceptance: Decimal | None
    cost_metrics: tuple[CostMetric, ...]
    latency_metrics: tuple[LatencyMetric, ...]


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    return None if denominator == 0 else Decimal(numerator) / Decimal(denominator)


def evaluate_metrics(
    records: tuple[EvaluationRecord, ...], repeat_groups: tuple[RepeatGroup, ...] = ()
) -> EvaluationMetrics:
    tp = sum(record.label is EvaluationLabel.TP for record in records)
    fp = sum(record.label is EvaluationLabel.FP for record in records)
    fn = sum(record.label is EvaluationLabel.FN for record in records)
    tn = sum(record.label is EvaluationLabel.TN for record in records)
    abstentions = sum(record.label is EvaluationLabel.ABSTAIN for record in records)
    malformed = sum(record.malformed_attempts for record in records)
    recorded = sum(record.recorded_attempts for record in records)
    accepted = sum(record.reviewer_label is ReviewerLabel.ACCEPTED for record in records)
    rejected = sum(record.reviewer_label is ReviewerLabel.REJECTED for record in records)
    consistent = sum(len({output for output in group.output_bytes}) == 1 for group in repeat_groups)
    cost_values: dict[tuple[str, str], list[Decimal]] = {}
    latency_values: dict[str, list[Decimal]] = {}
    for record in records:
        if (
            record.cost.amount is not None
            and record.cost.unit is not None
            and record.cost.currency is not None
        ):
            cost_values.setdefault((record.cost.unit, record.cost.currency), []).append(
                record.cost.amount
            )
        if record.latency.value is not None and record.latency.unit is not None:
            latency_values.setdefault(record.latency.unit, []).append(record.latency.value)
    cost_metrics = tuple(
        CostMetric(
            unit,
            currency,
            len(values),
            sum(values, Decimal("0")),
            sum(values, Decimal("0")) / len(values),
        )
        for (unit, currency), values in sorted(cost_values.items())
    )
    latency_metrics = tuple(
        LatencyMetric(
            unit,
            len(values),
            sum(values, Decimal("0")),
            sum(values, Decimal("0")) / len(values),
        )
        for unit, values in sorted(latency_values.items())
    )
    return EvaluationMetrics(
        DISCOVERY_EVALUATION_LABELS_VERSION,
        tp,
        fp,
        fn,
        tn,
        abstentions,
        len(records),
        malformed,
        recorded,
        consistent,
        len(repeat_groups),
        accepted,
        rejected,
        _ratio(tp, tp + fp),
        _ratio(tp, tp + fn),
        _ratio(fp, fp + tn),
        _ratio(abstentions, len(records)),
        _ratio(malformed, recorded),
        _ratio(consistent, len(repeat_groups)),
        _ratio(accepted, accepted + rejected),
        cost_metrics,
        latency_metrics,
    )


__all__ = [
    "DISCOVERY_EVALUATION_LABELS_VERSION",
    "CostMetric",
    "EvaluationLabel",
    "EvaluationMetrics",
    "EvaluationRecord",
    "LatencyMetric",
    "RepeatGroup",
    "ReviewerLabel",
    "evaluate_metrics",
]
