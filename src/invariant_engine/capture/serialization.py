"""Stable safe serialization for producer-trusted capture results."""

from __future__ import annotations

from invariant_engine.capture.models import CaptureBatchResult, is_trusted_batch
from invariant_engine.capture.specification import specification_fingerprint
from invariant_engine.domain.errors import DomainError
from invariant_engine.serialization import stable_json_bytes, stable_json_text


class CaptureSerializationError(DomainError):
    """Capture material is untrusted, mutated, misbound, or contradictory."""


def _validate(value: object) -> CaptureBatchResult:
    if not is_trusted_batch(value):
        raise CaptureSerializationError("capture batch is not producer-trusted and intact")
    assert isinstance(value, CaptureBatchResult)
    if value.specification is not None:
        try:
            fingerprint = specification_fingerprint(value.specification)
        except Exception as exc:
            raise CaptureSerializationError("capture specification is no longer valid") from exc
        if fingerprint != value.specification_fingerprint:
            raise CaptureSerializationError("capture specification fingerprint mismatch")
        for position, attempt in enumerate(value.attempts):
            if (
                attempt.target.position != position
                or attempt.target != value.specification.targets[position]
                or attempt.specification_fingerprint != fingerprint
            ):
                raise CaptureSerializationError(
                    "capture attempt is omitted, reordered, or misbound"
                )
    return value


def serialize_capture_bytes(value: object) -> bytes:
    return stable_json_bytes(_validate(value))


def serialize_capture_text(value: object) -> str:
    return stable_json_text(_validate(value))


__all__ = ["CaptureSerializationError", "serialize_capture_bytes", "serialize_capture_text"]
