from __future__ import annotations

import copy
import pickle

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
    is_trusted_attempt,
    is_trusted_batch,
    serialize_capture_bytes,
)
from invariant_engine.constraints import TrustedQuoteObservation
from invariant_engine.diagnostics import SuccessfulHistoricalValidationRecord
from invariant_engine.opportunities import OpportunityCandidate
from invariant_engine.provenance import RawEnvelope
from invariant_engine.relationships import RelationshipCertificate


def produced_result(fixed_clock):
    return capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )


def test_process_local_trust_does_not_transfer_through_copy_pickle_or_json(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    assert is_trusted_batch(result)
    assert is_trusted_attempt(result.attempts[0])
    for transferred in (
        copy.copy(result),
        copy.deepcopy(result),
        pickle.loads(pickle.dumps(result)),
    ):
        assert not is_trusted_batch(transferred)
        with pytest.raises(CaptureSerializationError):
            serialize_capture_bytes(transferred)
    assert isinstance(__import__("json").loads(serialize_capture_bytes(result)), dict)


def test_material_mutation_revokes_trust(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    object.__setattr__(result.attempts[0], "reason_code", "changed")
    assert not is_trusted_attempt(result.attempts[0])
    assert not is_trusted_batch(result)


def test_capture_artifacts_cannot_impersonate_historical_trust_types(fixed_clock) -> None:
    attempt = produced_result(fixed_clock).attempts[0]
    protected = (
        RawEnvelope,
        RelationshipCertificate,
        TrustedQuoteObservation,
        OpportunityCandidate,
        SuccessfulHistoricalValidationRecord,
    )
    assert not isinstance(attempt, protected)


def test_each_contradictory_state_mutation_revokes_attempt_and_batch_trust(fixed_clock) -> None:
    mutations = (
        ("acquisition_started", False),
        ("normal_completion", False),
        ("received_byte_count", 0),
        ("retained_byte_count", 0),
        ("retained_body_sha256", "0" * 64),
        ("dispatch_count", 0),
        ("status", "captured"),
        ("suppression_source", "body"),
    )
    for field, value in mutations:
        result = produced_result(fixed_clock)
        object.__setattr__(result.attempts[0], field, value)
        assert not is_trusted_attempt(result.attempts[0])
        assert not is_trusted_batch(result)


def test_attempt_identity_position_and_specification_binding_are_committed(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    object.__setattr__(result.attempts[0].target, "position", 1)
    assert not is_trusted_attempt(result.attempts[0])
    with pytest.raises(CaptureSerializationError):
        serialize_capture_bytes(result)
