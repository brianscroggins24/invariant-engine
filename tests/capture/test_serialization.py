from __future__ import annotations

import hashlib
import json

import pytest

from conftest import (
    SIGNATURE,
    capture_batch,
    complete_transport,
    kalshi_body,
    kalshi_target,
    polymarket_body,
    polymarket_target,
    polymarket_us_body,
    polymarket_us_target,
    specification,
    specification_v2,
)
from invariant_engine.capture import (
    CAPTURE_RESULT_SCHEMA_VERSION,
    CAPTURE_RESULT_SCHEMA_VERSION_V2,
    AcquisitionOutcome,
    BatchStatus,
    CaptureEnvironment,
    CaptureSerializationError,
    KalshiAuthenticationBinding,
    RetentionState,
    TargetStatus,
    TransportFailureKind,
    TransportResult,
    serialize_capture_bytes,
    serialize_capture_text,
)
from invariant_engine.capture.specification import KALSHI_DEMO_ORIGIN


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


def test_v1_success_and_outer_failure_bytes_and_identities_match_goldens(fixed_clock) -> None:
    success = capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )
    invalid = capture_batch(
        specification(polymarket_target(1)),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )
    missing_authentication = capture_batch(
        specification(kalshi_target()),
        transport=lambda *a, **k: complete_transport(b"{}"),
        observer_clock=fixed_clock,
    )
    assert success.schema_version == CAPTURE_RESULT_SCHEMA_VERSION
    assert success.batch_id == (
        "capture-batch:005f98d810df3c51445ccf48be55bbdf6d5c2670b79c33a4d2e6400f2411b294"
    )
    assert success.attempts[0].attempt_id == (
        "capture-attempt:af4e313d178d6255e6498023296b34a95f7f6173795c748a4f541f0038fc3f64"
    )
    assert hashlib.sha256(serialize_capture_bytes(success)).hexdigest() == (
        "aeec02ada4487c08ecb672bb27f5da782306f538c42ee0f27e773259921651e8"
    )
    assert invalid.batch_id == (
        "capture-batch:56259467fa5ae6d955e97ea3d8eebf74e9760b59e8cd6cbc2dbdd01f1b979972"
    )
    assert hashlib.sha256(serialize_capture_bytes(invalid)).hexdigest() == (
        "3f158bbada6d07e589b1fe6ed49fa4ec758b3002fd83e9e7829bd94af87c57d1"
    )
    assert missing_authentication.batch_id == (
        "capture-batch:8f3febfe54ee5ea9adf5d8d6004f72f38c3fb834473f2e1e5b0d0fe65f3b971e"
    )
    assert hashlib.sha256(serialize_capture_bytes(missing_authentication)).hexdigest() == (
        "7bcbfa4eadc589188afcf13d4af9a0f1fc715aac818123e904694f8f0656296b"
    )


def test_v1_remaining_target_failures_and_signed_kalshi_success_match_baseline_goldens(
    fixed_clock,
) -> None:
    def execute(response: TransportResult):
        return capture_batch(
            specification(polymarket_target()),
            transport=lambda *a, **k: response,
            observer_clock=fixed_clock,
        )

    def zero_body_failure(
        failure: TransportFailureKind,
        outcome: AcquisitionOutcome,
        *,
        status: int | None,
    ) -> TransportResult:
        return TransportResult(
            failure,
            status,
            None,
            None,
            outcome,
            RetentionState.ABSENT,
            0,
            None,
            None,
            None,
        )

    mutated_specification = specification(polymarket_target())

    def mutate_during_transport(*args, **kwargs):
        object.__setattr__(mutated_specification, "specification_id", "mutated/spec")
        return complete_transport(polymarket_body())

    integrity_failure = capture_batch(
        mutated_specification,
        transport=mutate_during_transport,
        observer_clock=fixed_clock,
    )
    signing_failure = capture_batch(
        specification(kalshi_target()),
        (
            KalshiAuthenticationBinding(
                CaptureEnvironment.DEMO,
                KALSHI_DEMO_ORIGIN,
                "key-1",
                lambda _: "bad",
            ),
        ),
        transport=lambda *a, **k: complete_transport(kalshi_body()),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "123",
    )
    partial = b'{"partial":'
    cases = {
        TargetStatus.CONFIDENTIALITY_FAILURE: execute(
            TransportResult(
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
        ),
        TargetStatus.INTEGRITY_FAILURE: integrity_failure,
        TargetStatus.SIGNING_FAILED: signing_failure,
        TargetStatus.RESPONSE_HEADERS_INVALID: execute(
            zero_body_failure(
                TransportFailureKind.HEADERS,
                AcquisitionOutcome.NOT_STARTED,
                status=200,
            )
        ),
        TargetStatus.BODY_OVERSIZED: execute(
            TransportResult(
                TransportFailureKind.OVERSIZED,
                200,
                1_048_577,
                "application/json",
                AcquisitionOutcome.NOT_STARTED,
                RetentionState.ABSENT,
                0,
                None,
                None,
                None,
            )
        ),
        TargetStatus.BODY_PARTIAL: execute(
            TransportResult(
                TransportFailureKind.PARTIAL,
                200,
                None,
                "application/json",
                AcquisitionOutcome.PARTIAL,
                RetentionState.PARTIAL,
                len(partial),
                partial,
                hashlib.sha256(partial).hexdigest(),
                None,
            )
        ),
        TargetStatus.TIMEOUT: execute(
            zero_body_failure(
                TransportFailureKind.TIMEOUT,
                AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
                status=None,
            )
        ),
        TargetStatus.TLS_OR_TRANSPORT_FAILED: execute(
            zero_body_failure(
                TransportFailureKind.TRANSPORT,
                AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
                status=None,
            )
        ),
        TargetStatus.HTTP_STATUS_UNSUPPORTED: execute(complete_transport(b"{}", 404)),
        TargetStatus.BODY_EMPTY: execute(complete_transport(b"")),
        TargetStatus.UTF8_INVALID: execute(complete_transport(b"\xff")),
        TargetStatus.JSON_INVALID: execute(complete_transport(b"{")),
        TargetStatus.SCHEMA_INVALID: execute(complete_transport(b"{}")),
        TargetStatus.IDENTIFIER_MISMATCH: execute(complete_transport(polymarket_body("456"))),
    }
    expected = {
        TargetStatus.CONFIDENTIALITY_FAILURE: (
            "capture-batch:c2f4338fad411e944291961057f2b69f71d0e013030201a28d879106634673e0",
            "capture-attempt:6907f2422786b85acfc5050c32319924da56b5c219e452f5c00abb342025ecea",
            "822a137fbd8e74f3da728c4569dc12b97fe65913c629ef97740c7b5fba1b44db",
        ),
        TargetStatus.INTEGRITY_FAILURE: (
            "capture-batch:7811b1b8226eee31f88e929a1b66954c47f0d60cf1b1071c6e28aa44f0f9e2ea",
            "capture-attempt:ed7333f2859a8e98b1eece9bab605f3c54969df2667e4c9138c5b422138c962c",
            "4a93286864d7e6f3d33e0e6adcd33bdea2753be5d061c3144ef7875b4759a471",
        ),
        TargetStatus.SIGNING_FAILED: (
            "capture-batch:540614105a21c99eabbd1ee5f7d066a715fca58d52a30f3ee175dc78da974ec7",
            "capture-attempt:ac6500df2cc8b8fbb2197d16e5c73f5467f3d061c333d41d2e2a31f244a4a842",
            "9712601d225eec013b11c5dfa613a055b0a72b1b088a1e38ba3e94bbafe1ff78",
        ),
        TargetStatus.RESPONSE_HEADERS_INVALID: (
            "capture-batch:85c1dc0cd4c147e5aa89a808de467637fb3739d3ce06d24cde450eaaaa760153",
            "capture-attempt:5a17087eee4ae7c17dfaf7fc86c2116f4bebf3f56ec64eeb47484da4957b7953",
            "68d296a0bfe3084b6b63bb5d57b5e5fbf2bd961303fa00d3aa39696fae9ef7a9",
        ),
        TargetStatus.BODY_OVERSIZED: (
            "capture-batch:10da1010e7d427c7d804e7dd13dcf1d64a5119617a7145d89d7d49bbf19c259d",
            "capture-attempt:e38567cd2c78e13a4d02bc7be6dc926e26d3f50357a9f26ad8e1c813ff53bca6",
            "aa4d03f721bd0f9ebbd6441a2ba3cc3596ec55cab28e3a2b11b5adfcb8351229",
        ),
        TargetStatus.BODY_PARTIAL: (
            "capture-batch:dc178f2d7c5f6ca63766524c9cd30db07d0d42e36c63268d6d0a9363996b5fe7",
            "capture-attempt:83a57f3fa55b54a86221686756e801a7248a56b4c939ef7f80a4819afd72501d",
            "177056b5cf59efaa6ef0fcf434c8ecf89872baa46fe0cc541e4259a929ba3466",
        ),
        TargetStatus.TIMEOUT: (
            "capture-batch:af125260ee760708dbac98dab6455cf6a3b8d24e3199cb71611633896d172e2e",
            "capture-attempt:13c9db46350eb7e9b3654dc20c167995c8a85b916c78c7ef00daa7071babd07c",
            "b7150572f098dc4790e2057d6a06c14e1978dc21587017e903db5a3d90e812d6",
        ),
        TargetStatus.TLS_OR_TRANSPORT_FAILED: (
            "capture-batch:2422ead7bb4978860648d6e7ff8918cc5bea724409ba4011f5be52b4085969de",
            "capture-attempt:d3388004ec45e052e1e816cd1fb281c5cb869ad70f99647ed9c2a89a2011126d",
            "e5c4a35611b3fb0a0914026650a9b63170cc21d8140e871f93f32599f99a9e38",
        ),
        TargetStatus.HTTP_STATUS_UNSUPPORTED: (
            "capture-batch:266d9ebf8f1a6ae6d2594ac4563379423aac07c44bcb5838874b0b0db304f6e4",
            "capture-attempt:53b1d215c409b58014588e523a48148a3dda6d1cb4d4406b9ac3892b3c8c845b",
            "4ddb32a20013880e5f9ec24d173026b2f589cabef6c86afa666a7b9420504655",
        ),
        TargetStatus.BODY_EMPTY: (
            "capture-batch:c2c59b7e4f7ef01debdd1a176a22f10435e30a4f84e93c4f0dbe34efbaa1f229",
            "capture-attempt:e6a7b98ac061348f6850efa5c33bb9ee3cb3a0fa229f6b33204f9b2e2d1fea35",
            "6ef22a36190157213ff114caa9d8e23bab1dceb096db5ec57dc3be7128f87aa3",
        ),
        TargetStatus.UTF8_INVALID: (
            "capture-batch:a4893621dffa2b32e7224efeee42dcb24553476e554ba286a2e20bd4391e6f5a",
            "capture-attempt:90b1ef10646b1db7332d4f2155dc4b77ac71700eb31efdc20286740ea97938ea",
            "e78f2d2a3c5ea94c21a208c98a71e2b3aae5057a4da0df410a2535574eeec713",
        ),
        TargetStatus.JSON_INVALID: (
            "capture-batch:cbf844bc00729a5fa57367f4fe95e084d0905cfb3331b7f1343b62be1aed8eaf",
            "capture-attempt:00f801839e5da9e1b8560044924fc0fcbdce40b11651e4037c50e58002ff9186",
            "24d26b76f2cd95821367645e5535add143f7a881a6878d79f31e785239b2b586",
        ),
        TargetStatus.SCHEMA_INVALID: (
            "capture-batch:b0cb8c7e12c56c21416b737a8685f186069cc36c6a92677bdea1d26cb9d8eece",
            "capture-attempt:f4ffb348460160bcfdfe940ba5346896ddc75e5e56a5fd3fe9fc83045f6f6365",
            "6a5836f93094639ac37bc6ef3d3be212af7d1a41435c4eb63a866a088162891c",
        ),
        TargetStatus.IDENTIFIER_MISMATCH: (
            "capture-batch:7b9b367d1b30c3b80b50e4b5c486c188af63b780d8bb2da16574eb8069e760ab",
            "capture-attempt:18eac2147b23c7188d5a9f2643f3bfcfbbc64359591306ba864fb9ec15fb71b4",
            "67baea431e86ec2e998483b48d06af6138bb26554ad25cf45216439bac43d838",
        ),
    }
    assert set(cases) == set(expected)
    for status, result in cases.items():
        assert result.status is BatchStatus.COMPLETED
        assert result.attempts[0].status is status
        expected_batch, expected_attempt, expected_serialized = expected[status]
        assert result.batch_id == expected_batch
        assert result.attempts[0].attempt_id == expected_attempt
        assert hashlib.sha256(serialize_capture_bytes(result)).hexdigest() == expected_serialized


def test_v1_signed_kalshi_success_and_outer_integrity_match_baseline_goldens(
    fixed_clock,
) -> None:
    signed_kalshi = capture_batch(
        specification(kalshi_target()),
        (
            KalshiAuthenticationBinding(
                CaptureEnvironment.DEMO,
                KALSHI_DEMO_ORIGIN,
                "key-1",
                lambda _: SIGNATURE,
            ),
        ),
        transport=lambda *a, **k: complete_transport(kalshi_body()),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "123",
    )
    outer_integrity = capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: object(),
        observer_clock=fixed_clock,
    )
    assert signed_kalshi.attempts[0].status is TargetStatus.CAPTURED
    assert signed_kalshi.batch_id == (
        "capture-batch:fdd64d31da1cad579a85b3623d687d3f97546146cd2f06ce890392fe1f9f2d9a"
    )
    assert signed_kalshi.attempts[0].attempt_id == (
        "capture-attempt:f8cd7620480182e977e58bd3fcdca1c34351acc723bfe1ceae18d3e61a2b296f"
    )
    assert hashlib.sha256(serialize_capture_bytes(signed_kalshi)).hexdigest() == (
        "8b4353238328e520beb30ffa6019fa20304ad449f6983219ca4b89265bc8069c"
    )
    assert outer_integrity.status is BatchStatus.INTEGRITY_FAILURE
    assert outer_integrity.attempts == ()
    assert outer_integrity.batch_id == (
        "capture-batch:568883220333fdb862e686adf295874072560d3b6ce3031d453827b92eff8800"
    )
    assert hashlib.sha256(serialize_capture_bytes(outer_integrity)).hexdigest() == (
        "4e89d47bbe2c1238f777201a2cfdf09050ffae45bfdb3fe7b1364e5fae92de95"
    )


def test_v2_serialization_is_stable_native_and_version_bound(fixed_clock) -> None:
    result = capture_batch(
        specification_v2(polymarket_us_target()),
        transport=lambda *a, **k: complete_transport(polymarket_us_body()),
        observer_clock=fixed_clock,
    )
    serialized = serialize_capture_bytes(result)
    assert serialized == serialize_capture_bytes(result)
    parsed = json.loads(serialized)
    assert parsed["schema_version"] == CAPTURE_RESULT_SCHEMA_VERSION_V2
    assert parsed["specification"]["schema_version"] == "capture-specification-v2"
    assert parsed["attempts"][0]["schema_version"] == CAPTURE_RESULT_SCHEMA_VERSION_V2
    book = parsed["attempts"][0]["order_book"]
    assert book["market_slug"] == "synthetic-market-1"
    assert [level["price_text"] for level in book["bids"]] == ["0.500", "0.500"]
    assert [level["currency"] for level in book["bids"]] == ["USD", "USD"]
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
