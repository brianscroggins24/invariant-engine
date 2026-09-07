from __future__ import annotations

import json

import pytest

from conftest import (
    capture_batch,
    complete_transport,
    polymarket_body,
    polymarket_target,
    specification,
)
from invariant_engine.capture import (
    CaptureSerializationError,
    serialize_capture_bytes,
    serialize_capture_text,
)


def test_serialization_is_stable_safe_and_versioned(fixed_clock) -> None:
    result = capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )
    first = serialize_capture_bytes(result)
    assert first == serialize_capture_bytes(result)
    assert first.decode() == serialize_capture_text(result)
    parsed = json.loads(first)
    assert parsed["schema_version"] == "capture-result-v1"
    assert parsed["attempts"][0]["observer_started_at"].endswith("Z")
    assert "runtime" not in parsed


def test_serialization_rejects_reordered_omitted_and_mutated_attempts(fixed_clock) -> None:
    result = capture_batch(
        specification(polymarket_target(0, "1"), polymarket_target(1, "2")),
        transport=lambda target, *a, **k: complete_transport(polymarket_body(target.identifier)),
        observer_clock=fixed_clock,
    )
    object.__setattr__(result, "attempts", tuple(reversed(result.attempts)))
    with pytest.raises(CaptureSerializationError):
        serialize_capture_bytes(result)


def test_suppressed_material_and_authentication_never_serialize(fixed_clock) -> None:
    from conftest import SIGNATURE, kalshi_target
    from invariant_engine.capture import (
        AcquisitionOutcome,
        CaptureEnvironment,
        KalshiAuthenticationBinding,
        RetentionState,
        TransportFailureKind,
        TransportResult,
    )
    from invariant_engine.capture.specification import KALSHI_DEMO_ORIGIN

    response = TransportResult(
        TransportFailureKind.CONFIDENTIALITY,
        200,
        None,
        None,
        AcquisitionOutcome.COMPLETED,
        RetentionState.SUPPRESSED,
        8,
        None,
        None,
        "body",
    )
    result = capture_batch(
        specification(kalshi_target()),
        (
            KalshiAuthenticationBinding(
                CaptureEnvironment.DEMO, KALSHI_DEMO_ORIGIN, "secret-key", lambda _: SIGNATURE
            ),
        ),
        transport=lambda *a, **k: response,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    serialized = serialize_capture_bytes(result)
    assert b"secret-key" not in serialized
    assert SIGNATURE.encode() not in serialized


def test_safe_outer_failure_is_serializable_without_untrusted_material(fixed_clock) -> None:
    result = capture_batch(
        specification(polymarket_target(1)),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )
    parsed = json.loads(serialize_capture_bytes(result))
    assert parsed["status"] == "specification_invalid"
    assert parsed["specification"] is None
    assert parsed["attempts"] == []
