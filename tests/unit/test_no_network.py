import socket
from datetime import UTC, datetime
from pathlib import Path

from invariant_engine.domain.ids import FixtureReference, Venue
from invariant_engine.provenance import RawEnvelope, SourceType
from invariant_engine.replay import replay_events
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiPriceConvention,
)
from invariant_engine.venues.kalshi import (
    parse_snapshot as parse_kalshi_snapshot,
)
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
)
from invariant_engine.venues.polymarket import (
    parse_snapshot as parse_polymarket_snapshot,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _envelope(path: Path, venue: Venue, name: str) -> RawEnvelope:
    return RawEnvelope.from_fixture_bytes(
        venue=venue,
        fixture=FixtureReference(name, venue),
        data=path.read_bytes(),
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=(
            POLYMARKET_DIRECT_SCHEMA_VERSION
            if venue is Venue.POLYMARKET
            else KALSHI_ORDERBOOK_SCHEMA_VERSION
        ),
    )


def test_representative_parsing_and_replay_attempt_no_outbound_socket(
    monkeypatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Milestone 1 attempted an outbound socket connection")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
    monkeypatch.setattr(socket, "create_connection", fail)

    polymarket_snapshot = _envelope(
        FIXTURES / "polymarket" / "orderbook_snapshot.json",
        Venue.POLYMARKET,
        "polymarket/network-boundary",
    )
    kalshi_snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/network-boundary",
    )

    assert parse_polymarket_snapshot(polymarket_snapshot).raw_ref == polymarket_snapshot.raw_ref
    assert (
        parse_kalshi_snapshot(
            kalshi_snapshot, price_convention=KalshiPriceConvention.OUTCOME_LEG
        ).raw_ref
        == kalshi_snapshot.raw_ref
    )
    assert replay_events([polymarket_snapshot]).validity.value == "valid"
    assert (
        replay_events(
            [kalshi_snapshot], kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG
        ).validity.value
        == "valid"
    )
