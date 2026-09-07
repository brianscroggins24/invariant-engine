"""Finite sequential one-shot capture batch orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, cast

from invariant_engine.capture.authentication import sign_target, validate_authentication_bindings
from invariant_engine.capture.models import (
    _PRODUCER_TOKEN,
    CAPTURE_RESULT_SCHEMA_VERSION,
    AcquisitionOutcome,
    BatchReasonCode,
    BatchStatus,
    CaptureBatchResult,
    CaptureSpecification,
    CaptureTarget,
    RetentionState,
    SuppressionSource,
    TargetAttempt,
    TargetReasonCode,
    TargetStatus,
    _issue_attempt,
    _issue_batch,
)
from invariant_engine.capture.parsing import ParseFailure, parse_order_book
from invariant_engine.capture.specification import (
    expected_origin,
    signing_path,
    specification_fingerprint,
    validate_specification,
)
from invariant_engine.capture.transport import TransportFailureKind, TransportResult, dispatch
from invariant_engine.domain.ids import Venue


class Transport(Protocol):
    def __call__(
        self,
        target: CaptureTarget,
        authentication_headers: tuple[tuple[str, str], ...] = (),
        *,
        confidentiality_values: tuple[str, ...] = (),
    ) -> TransportResult: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp() -> str:
    return str(time.time_ns() // 1_000_000)


def _outer_failure(status: BatchStatus, reason: BatchReasonCode) -> CaptureBatchResult:
    return _issue_batch(
        token=_PRODUCER_TOKEN,
        schema_version=CAPTURE_RESULT_SCHEMA_VERSION,
        status=status,
        reason_code=reason,
        specification=None,
        specification_fingerprint=None,
        attempts=(),
        provenance=(),
    )


def _attempt(
    *,
    specification_fingerprint_value: str,
    target: CaptureTarget,
    dispatch_count: int,
    status: TargetStatus,
    started: datetime,
    finished: datetime,
    transport: TransportResult | None = None,
    order_book: object = None,
) -> TargetAttempt:
    if type(target) is not CaptureTarget:
        raise ValueError("trusted target required")
    if transport is None:
        outcome = AcquisitionOutcome.NOT_STARTED
        retention = RetentionState.ABSENT
        http_status = None
        content_length = None
        content_type = None
        received = 0
        body = None
        digest = None
        suppression = None
    else:
        outcome = transport.acquisition_outcome
        retention = transport.retention_state
        http_status = transport.http_status
        content_length = transport.content_length
        content_type = transport.content_type
        received = transport.received_byte_count
        body = transport.retained_body
        digest = transport.retained_body_sha256
        suppression = (
            SuppressionSource(transport.suppression_source)
            if transport.suppression_source is not None
            else None
        )
    retained = len(body) if body is not None else 0
    return _issue_attempt(
        token=_PRODUCER_TOKEN,
        schema_version=CAPTURE_RESULT_SCHEMA_VERSION,
        specification_fingerprint=specification_fingerprint_value,
        target=target,
        dispatch_count=dispatch_count,
        status=status,
        reason_code=TargetReasonCode(status.value),
        observer_started_at=started,
        observer_finished_at=finished,
        http_status=http_status,
        content_length=content_length,
        content_type=content_type,
        acquisition_outcome=outcome,
        acquisition_started=outcome is not AcquisitionOutcome.NOT_STARTED,
        normal_completion=outcome is AcquisitionOutcome.COMPLETED,
        received_byte_count=received,
        retention_state=retention,
        retained_byte_count=retained,
        retained_body=body,
        retained_body_sha256=digest,
        suppression_source=suppression,
        order_book=order_book,
        provenance=target.provenance,
    )


def _transport_status(result: TransportResult) -> TargetStatus | None:
    if result.failure is None:
        return None
    mapping = {
        TransportFailureKind.CONFIDENTIALITY: TargetStatus.CONFIDENTIALITY_FAILURE,
        TransportFailureKind.HEADERS: TargetStatus.RESPONSE_HEADERS_INVALID,
        TransportFailureKind.OVERSIZED: TargetStatus.BODY_OVERSIZED,
        TransportFailureKind.PARTIAL: TargetStatus.BODY_PARTIAL,
        TransportFailureKind.TIMEOUT: TargetStatus.TIMEOUT,
        TransportFailureKind.TRANSPORT: TargetStatus.TLS_OR_TRANSPORT_FAILED,
    }
    return mapping.get(result.failure)


def _parse_status(failure: ParseFailure) -> TargetStatus:
    return {
        ParseFailure.UTF8_INVALID: TargetStatus.UTF8_INVALID,
        ParseFailure.JSON_INVALID: TargetStatus.JSON_INVALID,
        ParseFailure.SCHEMA_INVALID: TargetStatus.SCHEMA_INVALID,
        ParseFailure.IDENTIFIER_MISMATCH: TargetStatus.IDENTIFIER_MISMATCH,
    }[failure]


def _run_capture_batch(
    specification: object,
    authentication_bindings: object = (),
    *,
    transport: Transport = dispatch,
    observer_clock: Callable[[], datetime] = _now,
    timestamp_factory: Callable[[], str] = _timestamp,
) -> CaptureBatchResult:
    """Validate and execute one bounded batch with at most one dispatch per target."""

    try:
        validated = validate_specification(specification)
        fingerprint = specification_fingerprint(validated)
    except Exception:
        return _outer_failure(
            BatchStatus.SPECIFICATION_INVALID,
            BatchReasonCode.SPECIFICATION_INVALID,
        )
    try:
        bindings = validate_authentication_bindings(validated.targets, authentication_bindings)
    except Exception:
        return _outer_failure(
            BatchStatus.AUTHENTICATION_BINDING_INVALID,
            BatchReasonCode.AUTHENTICATION_BINDING_INVALID,
        )
    binding_material = {
        environment: (binding.environment, binding.origin, binding.key_id, id(binding.signer))
        for environment, binding in bindings.items()
    }
    original_specification = cast(CaptureSpecification, specification)
    attempts: list[TargetAttempt] = []
    for target in validated.targets:
        started = observer_clock()
        try:
            current_fingerprint = specification_fingerprint(original_specification)
        except Exception:
            current_fingerprint = ""
        if current_fingerprint != fingerprint:
            attempts.append(
                _attempt(
                    specification_fingerprint_value=fingerprint,
                    target=target,
                    dispatch_count=0,
                    status=TargetStatus.INTEGRITY_FAILURE,
                    started=started,
                    finished=observer_clock(),
                )
            )
            continue
        headers: tuple[tuple[str, str], ...] = ()
        secrets: tuple[str, ...] = ()
        if target.venue is Venue.KALSHI:
            binding = bindings[target.environment]
            before = binding_material[target.environment]
            current_binding = (
                binding.environment,
                binding.origin,
                binding.key_id,
                id(binding.signer),
            )
            if (
                current_binding != before
                or binding.environment is not target.environment
                or binding.origin != target.origin
                or binding.origin != expected_origin(target.venue, target.environment)
            ):
                attempts.append(
                    _attempt(
                        specification_fingerprint_value=fingerprint,
                        target=target,
                        dispatch_count=0,
                        status=TargetStatus.INTEGRITY_FAILURE,
                        started=started,
                        finished=observer_clock(),
                    )
                )
                continue
            try:
                timestamp = timestamp_factory()
                signed = sign_target(target, binding, timestamp)
            except BaseException:
                try:
                    failed_fingerprint = specification_fingerprint(original_specification)
                    failed_binding = (
                        binding.environment,
                        binding.origin,
                        binding.key_id,
                        id(binding.signer),
                    )
                    failure_status = (
                        TargetStatus.SIGNING_FAILED
                        if failed_fingerprint == fingerprint and failed_binding == before
                        else TargetStatus.INTEGRITY_FAILURE
                    )
                except Exception:
                    failure_status = TargetStatus.INTEGRITY_FAILURE
                attempts.append(
                    _attempt(
                        specification_fingerprint_value=fingerprint,
                        target=target,
                        dispatch_count=0,
                        status=failure_status,
                        started=started,
                        finished=observer_clock(),
                    )
                )
                continue
            try:
                after_fingerprint = specification_fingerprint(original_specification)
                after_binding = (
                    binding.environment,
                    binding.origin,
                    binding.key_id,
                    id(binding.signer),
                )
                binding_valid = (
                    before == after_binding
                    and binding.environment is target.environment
                    and binding.origin == target.origin
                    and binding.origin == expected_origin(target.venue, target.environment)
                    and signed.method == "GET"
                    and signed.path == signing_path(target)
                    and signed.timestamp == timestamp
                    and signed.headers
                    == (
                        ("KALSHI-ACCESS-KEY", binding.key_id),
                        ("KALSHI-ACCESS-TIMESTAMP", timestamp),
                        ("KALSHI-ACCESS-SIGNATURE", signed.headers[2][1]),
                    )
                )
            except Exception:
                binding_valid = False
                after_fingerprint = ""
            if after_fingerprint != fingerprint or not binding_valid:
                attempts.append(
                    _attempt(
                        specification_fingerprint_value=fingerprint,
                        target=target,
                        dispatch_count=0,
                        status=TargetStatus.INTEGRITY_FAILURE,
                        started=started,
                        finished=observer_clock(),
                    )
                )
                continue
            headers = signed.headers
            secrets = (binding.key_id, headers[2][1])
        try:
            response = transport(
                target,
                headers,
                confidentiality_values=secrets,
            )
            if type(response) is not TransportResult:
                raise TypeError
        except BaseException:
            return _outer_failure(
                BatchStatus.INTEGRITY_FAILURE,
                BatchReasonCode.UNTRUSTED_ACQUISITION_FACTS,
            )
        terminal = _transport_status(response)
        try:
            post_fingerprint = specification_fingerprint(original_specification)
        except Exception:
            post_fingerprint = ""
        if response.failure is TransportFailureKind.CONFIDENTIALITY:
            terminal = TargetStatus.CONFIDENTIALITY_FAILURE
        elif post_fingerprint != fingerprint:
            terminal = TargetStatus.INTEGRITY_FAILURE
        order_book: object = None
        if terminal is None:
            if response.http_status != 200:
                terminal = TargetStatus.HTTP_STATUS_UNSUPPORTED
            elif response.received_byte_count == 0:
                terminal = TargetStatus.BODY_EMPTY
            elif response.retained_body is None:
                return _outer_failure(
                    BatchStatus.INTEGRITY_FAILURE,
                    BatchReasonCode.UNTRUSTED_ACQUISITION_FACTS,
                )
            else:
                parsed = parse_order_book(target, response.retained_body)
                if parsed.failure is not None:
                    terminal = _parse_status(parsed.failure)
                else:
                    terminal = TargetStatus.CAPTURED
                    order_book = parsed.order_book
        try:
            attempts.append(
                _attempt(
                    specification_fingerprint_value=fingerprint,
                    target=target,
                    dispatch_count=1,
                    status=terminal,
                    started=started,
                    finished=observer_clock(),
                    transport=response,
                    order_book=order_book,
                )
            )
        except Exception:
            return _outer_failure(
                BatchStatus.INTEGRITY_FAILURE,
                BatchReasonCode.UNTRUSTED_ACQUISITION_FACTS,
            )
    return _issue_batch(
        token=_PRODUCER_TOKEN,
        schema_version=CAPTURE_RESULT_SCHEMA_VERSION,
        status=BatchStatus.COMPLETED,
        reason_code=BatchReasonCode.COMPLETED,
        specification=validated,
        specification_fingerprint=fingerprint,
        attempts=tuple(attempts),
        provenance=validated.provenance,
    )


def capture_batch(
    specification: object,
    authentication_bindings: object = (),
) -> CaptureBatchResult:
    """Execute through the fixed production transport and engine-owned clocks."""

    return _run_capture_batch(specification, authentication_bindings)


def _capture_batch_for_testing(
    specification: object,
    authentication_bindings: object = (),
    *,
    transport: Transport,
    observer_clock: Callable[[], datetime],
    timestamp_factory: Callable[[], str] = _timestamp,
) -> CaptureBatchResult:
    """Offline seam for tests; deliberately absent from the public package API."""

    return _run_capture_batch(
        specification,
        authentication_bindings,
        transport=transport,
        observer_clock=observer_clock,
        timestamp_factory=timestamp_factory,
    )


__all__ = ["capture_batch"]
