from datetime import UTC, datetime
from pathlib import Path

import pytest

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import FixtureReference, RawReference, Venue
from invariant_engine.provenance import RawEnvelope, SourceType
from invariant_engine.serialization import stable_json_bytes

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _envelope(path: Path, venue: Venue, name: str) -> RawEnvelope:
    return RawEnvelope.from_fixture_bytes(
        venue=venue,
        fixture=FixtureReference(name, venue),
        data=path.read_bytes(),
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://orderbook",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version="synthetic-v1",
    )


def test_raw_reference_and_hash_are_deterministic() -> None:
    path = FIXTURES / "polymarket" / "orderbook_snapshot.json"
    first = _envelope(path, Venue.POLYMARKET, "polymarket/orderbook_snapshot.json")
    second = _envelope(path, Venue.POLYMARKET, "polymarket/orderbook_snapshot.json")

    assert first.raw_ref == second.raw_ref
    assert first.payload_sha256 == second.payload_sha256
    assert stable_json_bytes(first) == stable_json_bytes(second)


def test_raw_payload_is_retained_immutably() -> None:
    envelope = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/orderbook_snapshot.json",
    )

    assert envelope.original_payload["msg"]["market_ticker"] == "SYNTHETIC-EVENT-MARKET"
    assert isinstance(envelope.original_payload["msg"]["yes_dollars_fp"], tuple)


def _direct_envelope(
    *,
    raw_ref: RawReference | None = None,
    venue: Venue = Venue.POLYMARKET,
    fixture: FixtureReference | None = None,
    capture_timestamp: datetime | None = None,
    retrieval_timestamp: datetime | None = None,
    payload_sha256: str = "0" * 64,
) -> RawEnvelope:
    return RawEnvelope(
        raw_ref=raw_ref or RawReference(f"sha256:{payload_sha256}", venue),
        venue=venue,
        source_type=SourceType.FIXTURE_REST,
        endpoint_or_channel="fixture://snapshot",
        capture_timestamp=capture_timestamp or datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        retrieval_timestamp=retrieval_timestamp,
        fixture=fixture or FixtureReference("fixture", venue),
        schema_version="synthetic-v1",
        original_payload={"nested": {"value": "preserved"}},
        payload_sha256=payload_sha256,
    )


def test_raw_envelope_rejects_malformed_digest() -> None:
    with pytest.raises(DomainError):
        _direct_envelope(payload_sha256="A" * 64)
    with pytest.raises(DomainError):
        _direct_envelope(payload_sha256="0" * 63)


def test_raw_envelope_rejects_reference_digest_mismatch() -> None:
    with pytest.raises(DomainError):
        _direct_envelope(raw_ref=RawReference("sha256:" + "1" * 64, Venue.POLYMARKET))


def test_raw_envelope_rejects_cross_venue_references_and_naive_time() -> None:
    with pytest.raises(DomainError):
        _direct_envelope(fixture=FixtureReference("fixture", Venue.KALSHI))
    with pytest.raises(DomainError):
        _direct_envelope(raw_ref=RawReference("sha256:" + "0" * 64, Venue.KALSHI))
    with pytest.raises(DomainError):
        _direct_envelope(capture_timestamp=datetime(2023, 11, 14, 22, 13, 20))
    with pytest.raises(DomainError):
        _direct_envelope(
            retrieval_timestamp=datetime(2023, 11, 14, 22, 13, 20),
        )


def test_direct_raw_payload_is_frozen_during_construction() -> None:
    envelope = _direct_envelope()

    with pytest.raises(TypeError):
        envelope.original_payload["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        envelope.original_payload["nested"]["value"] = "changed"  # type: ignore[index]
