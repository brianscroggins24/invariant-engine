"""Immutable models for the bounded Milestone 5 capture boundary."""

from __future__ import annotations

import hashlib
import weakref
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import SupportsIndex

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import Venue
from invariant_engine.serialization import stable_json_bytes

CAPTURE_SPECIFICATION_SCHEMA_VERSION = "capture-specification-v1"
CAPTURE_RESULT_SCHEMA_VERSION = "capture-result-v1"
MAX_BODY_BYTES = 1_048_576


class CaptureEnvironment(StrEnum):
    PRODUCTION = "production"
    DEMO = "demo"


class AcquisitionOutcome(StrEnum):
    NOT_STARTED = "not_started"
    FAILED_BEFORE_FIRST_BYTE = "failed_before_first_byte"
    COMPLETED = "completed"
    PARTIAL = "partial"
    OVERSIZED = "oversized"


class RetentionState(StrEnum):
    ABSENT = "absent"
    COMPLETE = "complete"
    PARTIAL = "partial"
    OVERSIZED = "oversized"
    SUPPRESSED = "suppressed"


class SuppressionSource(StrEnum):
    HEADER = "header"
    BODY = "body"


class TargetStatus(StrEnum):
    CONFIDENTIALITY_FAILURE = "confidentiality_failure"
    INTEGRITY_FAILURE = "integrity_failure"
    SIGNING_FAILED = "signing_failed"
    RESPONSE_HEADERS_INVALID = "response_headers_invalid"
    BODY_OVERSIZED = "body_oversized"
    BODY_PARTIAL = "body_partial"
    TIMEOUT = "timeout"
    TLS_OR_TRANSPORT_FAILED = "tls_or_transport_failed"
    HTTP_STATUS_UNSUPPORTED = "http_status_unsupported"
    BODY_EMPTY = "body_empty"
    UTF8_INVALID = "utf8_invalid"
    JSON_INVALID = "json_invalid"
    SCHEMA_INVALID = "schema_invalid"
    IDENTIFIER_MISMATCH = "identifier_mismatch"
    CAPTURED = "captured"


class TargetReasonCode(StrEnum):
    CONFIDENTIALITY_FAILURE = "confidentiality_failure"
    INTEGRITY_FAILURE = "integrity_failure"
    SIGNING_FAILED = "signing_failed"
    RESPONSE_HEADERS_INVALID = "response_headers_invalid"
    BODY_OVERSIZED = "body_oversized"
    BODY_PARTIAL = "body_partial"
    TIMEOUT = "timeout"
    TLS_OR_TRANSPORT_FAILED = "tls_or_transport_failed"
    HTTP_STATUS_UNSUPPORTED = "http_status_unsupported"
    BODY_EMPTY = "body_empty"
    UTF8_INVALID = "utf8_invalid"
    JSON_INVALID = "json_invalid"
    SCHEMA_INVALID = "schema_invalid"
    IDENTIFIER_MISMATCH = "identifier_mismatch"
    CAPTURED = "captured"


class BatchStatus(StrEnum):
    COMPLETED = "completed"
    SPECIFICATION_INVALID = "specification_invalid"
    AUTHENTICATION_BINDING_INVALID = "authentication_binding_invalid"
    INTEGRITY_FAILURE = "integrity_failure"
    CONFIDENTIALITY_FAILURE = "confidentiality_failure"


class BatchReasonCode(StrEnum):
    COMPLETED = "completed"
    SPECIFICATION_INVALID = "specification_invalid"
    AUTHENTICATION_BINDING_INVALID = "authentication_binding_invalid"
    UNTRUSTED_ACQUISITION_FACTS = "untrusted_acquisition_facts"
    UNTRUSTED_CONFIDENTIAL_MATERIAL = "untrusted_confidential_material"


@dataclass(frozen=True, slots=True)
class CaptureProvenance:
    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    connect_timeout_seconds: Decimal = Decimal("5.0")
    inactivity_timeout_seconds: Decimal = Decimal("5.0")
    elapsed_budget_seconds: Decimal = Decimal("20.0")
    max_header_fields: int = 100
    max_header_pair_bytes: int = 8_192
    max_header_bytes: int = 32_768
    max_body_bytes: int = MAX_BODY_BYTES
    body_chunk_bytes: int = 65_536


@dataclass(frozen=True, slots=True)
class CaptureTarget:
    position: int
    venue: Venue
    environment: CaptureEnvironment
    origin: str
    identifier: str
    limits: CaptureLimits
    provenance: tuple[CaptureProvenance, ...]


@dataclass(frozen=True, slots=True)
class CaptureSpecification:
    schema_version: str
    specification_id: str
    targets: tuple[CaptureTarget, ...]
    provenance: tuple[CaptureProvenance, ...]


@dataclass(frozen=True, slots=True)
class PriceLevel:
    price_text: str
    quantity_text: str
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class PolymarketOrderBook:
    market: str
    asset_id: str
    timestamp: str
    hash: str
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    min_order_size_text: str
    min_order_size: Decimal
    tick_size_text: str
    tick_size: Decimal
    neg_risk: bool
    last_trade_price_text: str
    last_trade_price: Decimal


@dataclass(frozen=True, slots=True)
class KalshiOrderBook:
    ticker: str
    yes_dollars: tuple[PriceLevel, ...]
    no_dollars: tuple[PriceLevel, ...]


CapturedOrderBook = PolymarketOrderBook | KalshiOrderBook


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class TargetAttempt:
    schema_version: str
    attempt_id: str
    specification_fingerprint: str
    target: CaptureTarget
    dispatch_count: int
    status: TargetStatus
    reason_code: TargetReasonCode
    observer_started_at: datetime
    observer_finished_at: datetime
    http_status: int | None
    content_length: int | None
    content_type: str | None
    acquisition_outcome: AcquisitionOutcome
    acquisition_started: bool
    normal_completion: bool
    received_byte_count: int
    retention_state: RetentionState
    retained_byte_count: int
    retained_body: bytes | None
    retained_body_sha256: str | None
    suppression_source: SuppressionSource | None
    order_book: CapturedOrderBook | None
    provenance: tuple[CaptureProvenance, ...]

    def __copy__(self) -> TargetAttempt:
        return _untrusted_attempt_clone(self)

    def __deepcopy__(self, memo: dict[int, object]) -> TargetAttempt:
        clone = _untrusted_attempt_clone(self)
        memo[id(self)] = clone
        return clone

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[object, tuple[object, ...]]:
        del protocol
        return (_untrusted_attempt_from_pickle, (self.attempt_id,))


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class CaptureBatchResult:
    schema_version: str
    batch_id: str
    status: BatchStatus
    reason_code: BatchReasonCode
    specification: CaptureSpecification | None
    specification_fingerprint: str | None
    attempts: tuple[TargetAttempt, ...]
    provenance: tuple[CaptureProvenance, ...]

    def __copy__(self) -> CaptureBatchResult:
        return _untrusted_batch_clone(self)

    def __deepcopy__(self, memo: dict[int, object]) -> CaptureBatchResult:
        clone = _untrusted_batch_clone(self)
        memo[id(self)] = clone
        return clone

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[object, tuple[object, ...]]:
        del protocol
        return (_untrusted_batch_from_pickle, (self.batch_id,))


@dataclass(frozen=True, slots=True)
class _TrustEntry:
    reference: weakref.ReferenceType[object]
    commitment: str


_PRODUCER_TOKEN = object()
_ATTEMPT_TRUST: dict[int, _TrustEntry] = {}
_BATCH_TRUST: dict[int, _TrustEntry] = {}


def _record_trust(registry: dict[int, _TrustEntry], value: object, commitment: str) -> None:
    key = id(value)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        entry = registry.get(key)
        if entry is not None and entry.reference is reference:
            registry.pop(key, None)

    registry[key] = _TrustEntry(weakref.ref(value, cleanup), commitment)


def _digest(value: object) -> str:
    return hashlib.sha256(stable_json_bytes(value)).hexdigest()


def _attempt_content(attempt: TargetAttempt) -> dict[str, object]:
    return {
        name: getattr(attempt, name)
        for name in TargetAttempt.__slots__
        if name not in {"attempt_id", "__weakref__"}
    }


def _batch_content(batch: CaptureBatchResult) -> dict[str, object]:
    return {
        name: getattr(batch, name)
        for name in CaptureBatchResult.__slots__
        if name not in {"batch_id", "__weakref__"}
    }


def _validate_attempt_state(attempt: TargetAttempt) -> None:
    if attempt.schema_version != CAPTURE_RESULT_SCHEMA_VERSION:
        raise DomainError("unsupported capture attempt version")
    if (
        type(attempt.status) is not TargetStatus
        or type(attempt.reason_code) is not TargetReasonCode
    ):
        raise DomainError("attempt status and reason must use closed enums")
    if attempt.status.value != attempt.reason_code.value:
        raise DomainError("attempt status and reason contradict")
    if type(attempt.target) is not CaptureTarget:
        raise DomainError("attempt target must use the exact target type")
    if (
        type(attempt.specification_fingerprint) is not str
        or len(attempt.specification_fingerprint) != 64
        or any(
            character not in "0123456789abcdef" for character in attempt.specification_fingerprint
        )
    ):
        raise DomainError("attempt requires a lowercase SHA-256 specification fingerprint")
    if type(attempt.provenance) is not tuple or attempt.provenance != attempt.target.provenance:
        raise DomainError("attempt provenance must exactly match target provenance")
    if (
        type(attempt.acquisition_outcome) is not AcquisitionOutcome
        or type(attempt.retention_state) is not RetentionState
    ):
        raise DomainError("acquisition and retention must use closed enums")
    if (
        attempt.suppression_source is not None
        and type(attempt.suppression_source) is not SuppressionSource
    ):
        raise DomainError("suppression source must use the closed enum")
    if (
        type(attempt.observer_started_at) is not datetime
        or type(attempt.observer_finished_at) is not datetime
    ):
        raise DomainError("observer timestamps must use exact datetime values")
    if (
        attempt.observer_started_at.tzinfo is None
        or attempt.observer_started_at.utcoffset() is None
        or attempt.observer_finished_at.tzinfo is None
        or attempt.observer_finished_at.utcoffset() is None
    ):
        raise DomainError("observer timestamps must be timezone-aware")
    if attempt.http_status is not None and (
        type(attempt.http_status) is not int or attempt.http_status < 0
    ):
        raise DomainError("HTTP status must be an exact nonnegative integer")
    if attempt.content_length is not None and (
        type(attempt.content_length) is not int or attempt.content_length < 0
    ):
        raise DomainError("Content-Length must be an exact nonnegative integer")
    if attempt.content_type is not None and type(attempt.content_type) is not str:
        raise DomainError("Content-Type metadata must be an exact string")
    if type(attempt.dispatch_count) is not int or attempt.dispatch_count not in (0, 1):
        raise DomainError("dispatch_count must be exact integer zero or one")
    if type(attempt.acquisition_started) is not bool or type(attempt.normal_completion) is not bool:
        raise DomainError("acquisition flags must be exact booleans")
    for value, field in (
        (attempt.received_byte_count, "received_byte_count"),
        (attempt.retained_byte_count, "retained_byte_count"),
    ):
        if type(value) is not int or value < 0:
            raise DomainError(f"{field} must be an exact nonnegative integer")
    expected_flags = {
        AcquisitionOutcome.NOT_STARTED: (False, False),
        AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE: (True, False),
        AcquisitionOutcome.COMPLETED: (True, True),
        AcquisitionOutcome.PARTIAL: (True, False),
        AcquisitionOutcome.OVERSIZED: (True, False),
    }
    if expected_flags[attempt.acquisition_outcome] != (
        attempt.acquisition_started,
        attempt.normal_completion,
    ):
        raise DomainError("acquisition flags contradict outcome")
    expected_retention = {
        AcquisitionOutcome.NOT_STARTED: RetentionState.ABSENT,
        AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE: RetentionState.ABSENT,
        AcquisitionOutcome.COMPLETED: RetentionState.COMPLETE,
        AcquisitionOutcome.PARTIAL: RetentionState.PARTIAL,
        AcquisitionOutcome.OVERSIZED: RetentionState.OVERSIZED,
    }
    if attempt.retention_state is RetentionState.SUPPRESSED:
        if attempt.status is not TargetStatus.CONFIDENTIALITY_FAILURE:
            raise DomainError("suppressed retention requires confidentiality failure")
        if attempt.suppression_source is None:
            raise DomainError("suppressed retention requires safe suppression source")
        if attempt.suppression_source is SuppressionSource.HEADER and (
            attempt.acquisition_outcome is not AcquisitionOutcome.NOT_STARTED
            or attempt.received_byte_count != 0
        ):
            raise DomainError("header suppression must precede body acquisition")
        if (
            attempt.suppression_source is SuppressionSource.BODY
            and attempt.acquisition_outcome
            not in {
                AcquisitionOutcome.COMPLETED,
                AcquisitionOutcome.PARTIAL,
                AcquisitionOutcome.OVERSIZED,
            }
        ):
            raise DomainError("body suppression requires acquired body bytes")
    elif attempt.retention_state is not expected_retention[attempt.acquisition_outcome]:
        raise DomainError("retention state contradicts acquisition outcome")
    elif attempt.suppression_source is not None:
        raise DomainError("suppression source requires suppressed retention")
    if (
        attempt.acquisition_outcome
        in {
            AcquisitionOutcome.NOT_STARTED,
            AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
        }
        and attempt.received_byte_count != 0
    ):
        raise DomainError("absent acquisition cannot have received bytes")
    if attempt.acquisition_outcome is AcquisitionOutcome.PARTIAL and not (
        1 <= attempt.received_byte_count <= MAX_BODY_BYTES
    ):
        raise DomainError("partial acquisition count is invalid")
    if (
        attempt.acquisition_outcome is AcquisitionOutcome.OVERSIZED
        and attempt.received_byte_count != MAX_BODY_BYTES + 1
    ):
        raise DomainError("oversized acquisition count is invalid")
    if attempt.acquisition_outcome is AcquisitionOutcome.COMPLETED and not (
        0 <= attempt.received_byte_count <= MAX_BODY_BYTES
    ):
        raise DomainError("completed acquisition count is invalid")
    if (
        attempt.acquisition_outcome is AcquisitionOutcome.COMPLETED
        and attempt.content_length is not None
        and attempt.content_length != attempt.received_byte_count
    ):
        raise DomainError("completed acquisition contradicts Content-Length")
    if (
        attempt.acquisition_outcome is AcquisitionOutcome.OVERSIZED
        and attempt.content_length is not None
    ):
        raise DomainError("streaming oversize cannot retain Content-Length metadata")
    if attempt.retention_state in {RetentionState.ABSENT, RetentionState.SUPPRESSED}:
        if (
            attempt.retained_byte_count != 0
            or attempt.retained_body is not None
            or attempt.retained_body_sha256 is not None
        ):
            raise DomainError("absent or suppressed retention cannot contain body material")
    else:
        if type(attempt.retained_body) is not bytes:
            raise DomainError("retained state requires exact bytes")
        body = attempt.retained_body
        if attempt.retained_byte_count != len(body):
            raise DomainError("retained byte count does not match body")
        if attempt.retained_body_sha256 != hashlib.sha256(body).hexdigest():
            raise DomainError("retained body digest mismatch")
        expected_length = (
            MAX_BODY_BYTES
            if attempt.retention_state is RetentionState.OVERSIZED
            else attempt.received_byte_count
        )
        if len(body) != expected_length:
            raise DomainError("retained body length contradicts acquisition")
    if attempt.status is TargetStatus.CAPTURED:
        if (
            attempt.dispatch_count != 1
            or attempt.http_status != 200
            or attempt.retention_state is not RetentionState.COMPLETE
            or attempt.received_byte_count == 0
            or attempt.order_book is None
        ):
            raise DomainError("captured status requires a complete parsed HTTP 200 body")
        if (
            attempt.target.venue is Venue.POLYMARKET
            and type(attempt.order_book) is not PolymarketOrderBook
        ):
            raise DomainError("captured Polymarket target requires its venue-native model")
        if attempt.target.venue is Venue.KALSHI and type(attempt.order_book) is not KalshiOrderBook:
            raise DomainError("captured Kalshi target requires its venue-native model")
    elif attempt.order_book is not None:
        raise DomainError("only captured attempts may contain an order book")
    if attempt.status is TargetStatus.CONFIDENTIALITY_FAILURE and (
        attempt.retention_state is not RetentionState.SUPPRESSED
        or attempt.suppression_source is None
        or attempt.content_length is not None
        or attempt.content_type is not None
    ):
        raise DomainError("confidentiality failure requires suppression of unsafe metadata")
    if attempt.status is TargetStatus.SIGNING_FAILED and not (
        attempt.dispatch_count == 0
        and attempt.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    ):
        raise DomainError("signing failure cannot dispatch or acquire")
    if attempt.status is TargetStatus.RESPONSE_HEADERS_INVALID and (
        attempt.acquisition_outcome is not AcquisitionOutcome.NOT_STARTED
    ):
        raise DomainError("header failure must precede body acquisition")
    if attempt.status is TargetStatus.BODY_OVERSIZED and not (
        (
            attempt.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
            and attempt.retention_state is RetentionState.ABSENT
        )
        or (
            attempt.acquisition_outcome is AcquisitionOutcome.OVERSIZED
            and attempt.retention_state is RetentionState.OVERSIZED
        )
    ):
        raise DomainError("body-oversized status contradicts acquisition")
    if (
        attempt.status is TargetStatus.BODY_OVERSIZED
        and attempt.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
        and (attempt.content_length is None or attempt.content_length <= MAX_BODY_BYTES)
    ):
        raise DomainError("declared oversized body requires an oversized Content-Length")
    if attempt.status is TargetStatus.BODY_PARTIAL and (
        attempt.acquisition_outcome is not AcquisitionOutcome.PARTIAL
    ):
        raise DomainError("body-partial status contradicts acquisition")
    if attempt.status in {TargetStatus.TIMEOUT, TargetStatus.TLS_OR_TRANSPORT_FAILED} and (
        attempt.acquisition_outcome
        not in {AcquisitionOutcome.NOT_STARTED, AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE}
    ):
        raise DomainError("zero-prefix transport status contradicts acquisition")
    if attempt.status is TargetStatus.HTTP_STATUS_UNSUPPORTED and (
        attempt.acquisition_outcome is not AcquisitionOutcome.COMPLETED
        or attempt.retention_state is not RetentionState.COMPLETE
        or attempt.http_status is None
        or attempt.http_status == 200
    ):
        raise DomainError("unsupported HTTP status contradicts acquisition")
    if attempt.status is TargetStatus.BODY_EMPTY and not (
        attempt.http_status == 200
        and attempt.acquisition_outcome is AcquisitionOutcome.COMPLETED
        and attempt.received_byte_count == 0
        and attempt.retention_state is RetentionState.COMPLETE
    ):
        raise DomainError("body-empty status contradicts acquisition facts")
    if attempt.status in {
        TargetStatus.UTF8_INVALID,
        TargetStatus.JSON_INVALID,
        TargetStatus.SCHEMA_INVALID,
        TargetStatus.IDENTIFIER_MISMATCH,
    } and not (
        attempt.http_status == 200
        and attempt.acquisition_outcome is AcquisitionOutcome.COMPLETED
        and attempt.retention_state is RetentionState.COMPLETE
        and attempt.received_byte_count > 0
    ):
        raise DomainError("parsing status requires a complete nonempty HTTP 200 body")


def _issue_attempt(*, token: object, **fields: object) -> TargetAttempt:
    if token is not _PRODUCER_TOKEN:
        raise DomainError("capture attempts may only be issued by the capture engine")
    value = object.__new__(TargetAttempt)
    for name in TargetAttempt.__slots__:
        if name not in {"attempt_id", "__weakref__"}:
            object.__setattr__(value, name, fields[name])
    _validate_attempt_state(value)
    digest = _digest(_attempt_content(value))
    object.__setattr__(value, "attempt_id", "capture-attempt:" + digest)
    _record_trust(_ATTEMPT_TRUST, value, digest)
    return value


def _issue_batch(*, token: object, **fields: object) -> CaptureBatchResult:
    if token is not _PRODUCER_TOKEN:
        raise DomainError("capture batches may only be issued by the capture engine")
    value = object.__new__(CaptureBatchResult)
    for name in CaptureBatchResult.__slots__:
        if name not in {"batch_id", "__weakref__"}:
            object.__setattr__(value, name, fields[name])
    _validate_batch_state(value)
    digest = _digest(_batch_content(value))
    object.__setattr__(value, "batch_id", "capture-batch:" + digest)
    _record_trust(_BATCH_TRUST, value, digest)
    return value


def _validate_batch_state(value: CaptureBatchResult) -> None:
    if value.schema_version != CAPTURE_RESULT_SCHEMA_VERSION:
        raise DomainError("unsupported capture batch version")
    if type(value.status) is not BatchStatus or type(value.reason_code) is not BatchReasonCode:
        raise DomainError("batch status and reason must use closed enums")
    expected_reason = {
        BatchStatus.COMPLETED: BatchReasonCode.COMPLETED,
        BatchStatus.SPECIFICATION_INVALID: BatchReasonCode.SPECIFICATION_INVALID,
        BatchStatus.AUTHENTICATION_BINDING_INVALID: BatchReasonCode.AUTHENTICATION_BINDING_INVALID,
        BatchStatus.INTEGRITY_FAILURE: BatchReasonCode.UNTRUSTED_ACQUISITION_FACTS,
        BatchStatus.CONFIDENTIALITY_FAILURE: BatchReasonCode.UNTRUSTED_CONFIDENTIAL_MATERIAL,
    }[value.status]
    if value.reason_code is not expected_reason:
        raise DomainError("batch status and reason contradict")
    if value.status is BatchStatus.COMPLETED:
        if (
            type(value.specification) is not CaptureSpecification
            or type(value.specification_fingerprint) is not str
            or len(value.specification_fingerprint) != 64
            or type(value.attempts) is not tuple
            or value.provenance != value.specification.provenance
        ):
            raise DomainError("completed batch requires specification identity")
    elif (
        value.specification is not None
        or value.specification_fingerprint is not None
        or value.attempts
        or value.provenance
    ):
        raise DomainError("outer failure may retain only safe batch identity")


def is_trusted_attempt(value: object) -> bool:
    if type(value) is not TargetAttempt:
        return False
    entry = _ATTEMPT_TRUST.get(id(value))
    try:
        _validate_attempt_state(value)
        digest = _digest(_attempt_content(value))
        return (
            entry is not None
            and entry.reference() is value
            and entry.commitment == digest
            and value.attempt_id == "capture-attempt:" + digest
        )
    except Exception:
        return False


def is_trusted_batch(value: object) -> bool:
    if type(value) is not CaptureBatchResult:
        return False
    entry = _BATCH_TRUST.get(id(value))
    try:
        _validate_batch_state(value)
        digest = _digest(_batch_content(value))
        if not (
            entry is not None
            and entry.reference() is value
            and entry.commitment == digest
            and value.batch_id == "capture-batch:" + digest
        ):
            return False
        if value.status is BatchStatus.COMPLETED:
            if value.specification is None or len(value.attempts) != len(
                value.specification.targets
            ):
                return False
            for target, attempt in zip(value.specification.targets, value.attempts, strict=True):
                if (
                    not is_trusted_attempt(attempt)
                    or attempt.target != target
                    or attempt.target.position != target.position
                    or attempt.specification_fingerprint != value.specification_fingerprint
                ):
                    return False
        elif value.attempts:
            return False
        return True
    except Exception:
        return False


def _untrusted_attempt_clone(value: TargetAttempt) -> TargetAttempt:
    clone = object.__new__(TargetAttempt)
    for name in TargetAttempt.__slots__:
        if name != "__weakref__":
            object.__setattr__(clone, name, getattr(value, name))
    return clone


def _untrusted_attempt_from_pickle(attempt_id: str) -> TargetAttempt:
    value = object.__new__(TargetAttempt)
    object.__setattr__(value, "attempt_id", attempt_id)
    return value


def _untrusted_batch_clone(value: CaptureBatchResult) -> CaptureBatchResult:
    clone = object.__new__(CaptureBatchResult)
    for name in CaptureBatchResult.__slots__:
        if name != "__weakref__":
            object.__setattr__(clone, name, getattr(value, name))
    return clone


def _untrusted_batch_from_pickle(batch_id: str) -> CaptureBatchResult:
    value = object.__new__(CaptureBatchResult)
    object.__setattr__(value, "batch_id", batch_id)
    return value


__all__ = [
    "AcquisitionOutcome",
    "BatchReasonCode",
    "BatchStatus",
    "CAPTURE_RESULT_SCHEMA_VERSION",
    "CAPTURE_SPECIFICATION_SCHEMA_VERSION",
    "CaptureBatchResult",
    "CaptureEnvironment",
    "CaptureLimits",
    "CaptureProvenance",
    "CaptureSpecification",
    "CaptureTarget",
    "KalshiOrderBook",
    "MAX_BODY_BYTES",
    "PolymarketOrderBook",
    "PriceLevel",
    "RetentionState",
    "SuppressionSource",
    "TargetAttempt",
    "TargetReasonCode",
    "TargetStatus",
    "is_trusted_attempt",
    "is_trusted_batch",
]
