"""Provider-neutral recorded response sources.

There is intentionally no live-provider implementation in this module.  A source
can only return bytes that were supplied in memory or read from a local path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from invariant_engine.discovery.parser import parse_strict_json_bytes
from invariant_engine.discovery.schema import DISCOVERY_FIXTURE_SCHEMA_VERSION
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} must be a non-empty string")
    return value


def _digest(data: bytes, field: str, expected: str) -> None:
    if expected != hashlib.sha256(data).hexdigest():
        raise DomainError(f"{field} does not match supplied bytes")


@dataclass(frozen=True, slots=True)
class RecordedParameter:
    name: str
    value: str

    def __post_init__(self) -> None:
        _nonempty(self.name, "parameter name")
        if not isinstance(self.value, str):
            raise DomainError("parameter value must be recorded as text")


@dataclass(frozen=True, slots=True)
class RecordedCost:
    amount: Decimal | None = None
    unit: str | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        if self.amount is not None and (
            not isinstance(self.amount, Decimal) or not self.amount.is_finite()
        ):
            raise DomainError("recorded cost amount must be a finite Decimal")
        for field in ("unit", "currency"):
            value = getattr(self, field)
            if value is not None:
                _nonempty(value, f"recorded cost {field}")


@dataclass(frozen=True, slots=True)
class RecordedLatency:
    value: Decimal | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and (
            not isinstance(self.value, Decimal) or not self.value.is_finite()
        ):
            raise DomainError("recorded latency must be a finite Decimal")
        if self.unit is not None:
            _nonempty(self.unit, "recorded latency unit")


@dataclass(frozen=True, slots=True)
class RecordedAttempt:
    attempt_index: int
    artifact_id: str
    artifact_sha256: str
    provider_label: str
    model_label: str
    model_version: str
    prompt_id: str
    prompt_version: str
    recorded_prompt: str | None
    prompt_digest: str | None
    parameters: tuple[RecordedParameter, ...]
    input_bytes: bytes
    input_sha256: str
    output_bytes: bytes
    output_sha256: str
    source_raw_refs: tuple[RawReference, ...]
    cost: RecordedCost
    latency: RecordedLatency
    input_schema_version: str
    output_schema_version: str
    fixture_schema_version: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_index, int) or isinstance(self.attempt_index, bool):
            raise DomainError("attempt_index must be an integer")
        if self.attempt_index < 0:
            raise DomainError("attempt_index must not be negative")
        for field in (
            "artifact_id",
            "artifact_sha256",
            "provider_label",
            "model_label",
            "model_version",
            "prompt_id",
            "prompt_version",
            "input_sha256",
            "output_sha256",
            "input_schema_version",
            "output_schema_version",
            "fixture_schema_version",
        ):
            _nonempty(getattr(self, field), field)
        if not isinstance(self.input_bytes, bytes) or not isinstance(self.output_bytes, bytes):
            raise DomainError("recorded input and output must be bytes")
        _digest(self.input_bytes, "input_sha256", self.input_sha256)
        _digest(self.output_bytes, "output_sha256", self.output_sha256)
        if len(self.artifact_sha256) != 64:
            raise DomainError("artifact_sha256 must be a SHA-256 digest")
        try:
            int(self.artifact_sha256, 16)
        except ValueError as exc:
            raise DomainError("artifact_sha256 must be hexadecimal") from exc
        if self.artifact_sha256 != self.artifact_sha256.lower():
            raise DomainError("artifact_sha256 must use lowercase hexadecimal")
        if self.recorded_prompt is None and self.prompt_digest is None:
            raise DomainError("recorded prompt or prompt digest is required")
        if self.recorded_prompt is not None:
            _nonempty(self.recorded_prompt, "recorded_prompt")
            computed = hashlib.sha256(self.recorded_prompt.encode("utf-8")).hexdigest()
            if self.prompt_digest is not None and self.prompt_digest != computed:
                raise DomainError("prompt_digest does not match recorded_prompt")
            object.__setattr__(self, "prompt_digest", computed)
        elif self.prompt_digest is not None:
            if len(self.prompt_digest) != 64 or self.prompt_digest != self.prompt_digest.lower():
                raise DomainError("prompt_digest must be a lowercase SHA-256 digest")
            try:
                int(self.prompt_digest, 16)
            except ValueError as exc:
                raise DomainError("prompt_digest must be hexadecimal") from exc
        for field in ("parameters", "source_raw_refs", "warnings"):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if any(not isinstance(item, RecordedParameter) for item in self.parameters):
            raise DomainError("parameters must contain RecordedParameter values")
        if any(not isinstance(item, RawReference) for item in self.source_raw_refs):
            raise DomainError("source_raw_refs must contain RawReference values")
        if any(not isinstance(item, str) or not item.strip() for item in self.warnings):
            raise DomainError("warnings must contain non-empty strings")


class RecordedResponseSource(Protocol):
    """The only source boundary accepted by discovery orchestration."""

    def read_attempts(self) -> tuple[RecordedAttempt, ...]: ...


@dataclass(frozen=True, slots=True)
class InMemoryRecordedResponseSource:
    recorded_attempts: tuple[RecordedAttempt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.recorded_attempts, tuple):
            object.__setattr__(self, "recorded_attempts", tuple(self.recorded_attempts))
        if any(not isinstance(item, RecordedAttempt) for item in self.recorded_attempts):
            raise DomainError("recorded_attempts must contain RecordedAttempt values")

    def read_attempts(self) -> tuple[RecordedAttempt, ...]:
        return self.recorded_attempts


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _raw_refs(value: object) -> tuple[RawReference, ...]:
    values = value if isinstance(value, list) else None
    if values is None:
        raise DomainError("fixture raw_refs must be an array")
    result: list[RawReference] = []
    for item in values:
        record = _mapping(item, "raw_ref")
        if set(record) != {"value", "venue"}:
            raise DomainError("fixture raw_ref has unexpected structure")
        try:
            venue = Venue(cast(str, record["venue"]))
        except (TypeError, ValueError) as exc:
            raise DomainError("fixture raw_ref has unsupported venue") from exc
        result.append(RawReference(cast(str, record["value"]), venue))
    return tuple(result)


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise DomainError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise DomainError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite():
        raise DomainError(f"{field} must be finite")
    return parsed


def _optional_text(record: dict[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is not None and not isinstance(value, str):
        raise DomainError(f"fixture {key} must be text when supplied")
    return value


@dataclass(frozen=True, slots=True)
class FixtureRecordedResponseSource:
    """Read recorded attempts from one local fixture artifact."""

    fixture_path: Path

    def read_attempts(self) -> tuple[RecordedAttempt, ...]:
        fixture_bytes = self.fixture_path.read_bytes()
        payload = parse_strict_json_bytes(fixture_bytes, "discovery fixture")
        record = _mapping(payload, "fixture")
        if set(record) != {"schema_version", "fixture_id", "attempts"}:
            raise DomainError("discovery fixture has unexpected structure")
        if record["schema_version"] != DISCOVERY_FIXTURE_SCHEMA_VERSION:
            raise DomainError("unsupported discovery fixture schema version")
        fixture_id = _nonempty(record["fixture_id"], "fixture_id")
        attempts_value = record["attempts"]
        if not isinstance(attempts_value, list):
            raise DomainError("fixture attempts must be an array")
        fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
        attempts: list[RecordedAttempt] = []
        allowed = {
            "attempt_index",
            "provider_label",
            "model_label",
            "model_version",
            "prompt_id",
            "prompt_version",
            "recorded_prompt",
            "prompt_digest",
            "parameters",
            "input_text",
            "output_text",
            "source_raw_refs",
            "cost",
            "latency",
            "input_schema_version",
            "output_schema_version",
            "fixture_schema_version",
            "warnings",
        }
        for item in attempts_value:
            attempt = _mapping(item, "fixture attempt")
            if set(attempt) != allowed:
                raise DomainError("fixture attempt has unexpected structure")
            parameters_value = attempt["parameters"]
            if not isinstance(parameters_value, list):
                raise DomainError("fixture parameters must be an array")
            parameters: list[RecordedParameter] = []
            for parameter in parameters_value:
                parameter_record = _mapping(parameter, "parameter")
                if set(parameter_record) != {"name", "value"}:
                    raise DomainError("fixture parameter has unexpected structure")
                parameters.append(
                    RecordedParameter(
                        cast(str, parameter_record["name"]),
                        cast(str, parameter_record["value"]),
                    )
                )
            cost_record = _mapping(attempt["cost"], "cost")
            if set(cost_record) != {"amount", "unit", "currency"}:
                raise DomainError("fixture cost has unexpected structure")
            latency_record = _mapping(attempt["latency"], "latency")
            if set(latency_record) != {"value", "unit"}:
                raise DomainError("fixture latency has unexpected structure")
            warnings = attempt["warnings"]
            if not isinstance(warnings, list):
                raise DomainError("fixture warnings must be an array")
            input_text = attempt["input_text"]
            output_text = attempt["output_text"]
            if not isinstance(input_text, str) or not isinstance(output_text, str):
                raise DomainError("fixture input_text and output_text must be text")
            input_bytes = input_text.encode("utf-8")
            output_bytes = output_text.encode("utf-8")
            attempts.append(
                RecordedAttempt(
                    attempt_index=cast(int, attempt["attempt_index"]),
                    artifact_id=fixture_id,
                    artifact_sha256=fixture_sha256,
                    provider_label=cast(str, attempt["provider_label"]),
                    model_label=cast(str, attempt["model_label"]),
                    model_version=cast(str, attempt["model_version"]),
                    prompt_id=cast(str, attempt["prompt_id"]),
                    prompt_version=cast(str, attempt["prompt_version"]),
                    recorded_prompt=_optional_text(attempt, "recorded_prompt"),
                    prompt_digest=_optional_text(attempt, "prompt_digest"),
                    parameters=tuple(parameters),
                    input_bytes=input_bytes,
                    input_sha256=hashlib.sha256(input_bytes).hexdigest(),
                    output_bytes=output_bytes,
                    output_sha256=hashlib.sha256(output_bytes).hexdigest(),
                    source_raw_refs=_raw_refs(attempt["source_raw_refs"]),
                    cost=RecordedCost(
                        _decimal(cost_record["amount"], "cost.amount")
                        if cost_record["amount"] is not None
                        else None,
                        _optional_text(cost_record, "unit"),
                        _optional_text(cost_record, "currency"),
                    ),
                    latency=RecordedLatency(
                        _decimal(latency_record["value"], "latency.value")
                        if latency_record["value"] is not None
                        else None,
                        _optional_text(latency_record, "unit"),
                    ),
                    input_schema_version=cast(str, attempt["input_schema_version"]),
                    output_schema_version=cast(str, attempt["output_schema_version"]),
                    fixture_schema_version=cast(str, attempt["fixture_schema_version"]),
                    warnings=tuple(cast(str, item) for item in warnings),
                )
            )
        return tuple(attempts)


__all__ = [
    "FixtureRecordedResponseSource",
    "InMemoryRecordedResponseSource",
    "RecordedAttempt",
    "RecordedCost",
    "RecordedLatency",
    "RecordedParameter",
    "RecordedResponseSource",
]
