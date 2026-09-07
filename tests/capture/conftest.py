from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pytest

from invariant_engine.capture import (
    CAPTURE_SPECIFICATION_SCHEMA_VERSION,
    AcquisitionOutcome,
    CaptureEnvironment,
    CaptureLimits,
    CaptureProvenance,
    CaptureSpecification,
    CaptureTarget,
    RetentionState,
    TransportResult,
)
from invariant_engine.capture.batch import _capture_batch_for_testing
from invariant_engine.capture.specification import KALSHI_DEMO_ORIGIN, POLYMARKET_ORIGIN
from invariant_engine.domain.ids import Venue

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
SIGNATURE = base64.b64encode(b"s" * 128).decode("ascii")
capture_batch = _capture_batch_for_testing


def polymarket_target(position: int = 0, identifier: str = "123") -> CaptureTarget:
    return CaptureTarget(
        position,
        Venue.POLYMARKET,
        CaptureEnvironment.PRODUCTION,
        POLYMARKET_ORIGIN,
        identifier,
        CaptureLimits(),
        (CaptureProvenance("case", f"polymarket-{position}"),),
    )


def kalshi_target(position: int = 0, identifier: str = "TEST-1") -> CaptureTarget:
    return CaptureTarget(
        position,
        Venue.KALSHI,
        CaptureEnvironment.DEMO,
        KALSHI_DEMO_ORIGIN,
        identifier,
        CaptureLimits(),
        (CaptureProvenance("case", f"kalshi-{position}"),),
    )


def specification(*targets: CaptureTarget) -> CaptureSpecification:
    return CaptureSpecification(
        CAPTURE_SPECIFICATION_SCHEMA_VERSION,
        "synthetic/spec-1",
        targets,
        (CaptureProvenance("fixture", "capture/cases"),),
    )


def polymarket_body(asset_id: str = "123") -> bytes:
    return (
        '{"market":"m","asset_id":"' + asset_id + '","timestamp":"opaque","hash":"h","bids":['
        '{"price":"0.50","size":"2.0"},{"price":"0.50","size":"1.0"}],'
        '"asks":[{"price":"0.51","size":"3.0"}],"min_order_size":"1",'
        '"tick_size":"0.01","neg_risk":false,"last_trade_price":"0.50"}'
    ).encode()


def kalshi_body() -> bytes:
    return (
        b'{"orderbook_fp":{"yes_dollars":[["0.40","2.00"],["0.40","1.00"]],'
        b'"no_dollars":[["0.59","3.00"]]}}'
    )


def complete_transport(body: bytes, status: int = 200) -> TransportResult:
    return TransportResult(
        None,
        status,
        len(body),
        "application/json",
        AcquisitionOutcome.COMPLETED,
        RetentionState.COMPLETE,
        len(body),
        body,
        hashlib.sha256(body).hexdigest(),
        None,
    )


@pytest.fixture
def fixed_clock():
    return lambda: NOW


@pytest.fixture
def valid_signature() -> str:
    return SIGNATURE
