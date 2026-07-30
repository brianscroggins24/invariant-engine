from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invariant_engine.domain.errors import ReplayError
from invariant_engine.domain.ids import FixtureReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.provenance import RawEnvelope, SourceType
from invariant_engine.replay import replay_events
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiPriceConvention,
)
from invariant_engine.venues.polymarket import POLYMARKET_DIRECT_SCHEMA_VERSION

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


def test_repeated_polymarket_replay_is_identical() -> None:
    events = [
        _envelope(
            FIXTURES / "polymarket" / "orderbook_snapshot.json",
            Venue.POLYMARKET,
            "polymarket/orderbook_snapshot.json",
        ),
        _envelope(
            FIXTURES / "polymarket" / "price_change.json",
            Venue.POLYMARKET,
            "polymarket/price_change.json",
        ),
    ]

    first = replay_events(events)
    second = replay_events(events)

    assert stable_json_bytes(first) == stable_json_bytes(second)
    assert first.final_state.order_book.asks.levels[0].price == Decimal("0.60")
    assert first.final_state.order_book.bids.levels[0].size == 7
    assert first.frames[0].sequence is None
    assert first.validity is StateValidity.VALID
    assert first.final_state.order_book.raw_refs == (
        events[0].raw_ref,
        events[1].raw_ref,
    )


def test_kalshi_delta_updates_native_book_and_sequence() -> None:
    events = [
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            "kalshi/orderbook_snapshot.json",
        ),
        _envelope(
            FIXTURES / "kalshi" / "orderbook_delta.json",
            Venue.KALSHI,
            "kalshi/orderbook_delta.json",
        ),
    ]

    result = replay_events(events, kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG)

    assert result.final_state.yes_side.levels[0].size == 2
    assert result.final_state.sequence == 11
    assert result.final_state.raw_ref == events[1].raw_ref
    assert result.final_state.raw_refs == (events[0].raw_ref, events[1].raw_ref)
    assert result.final_state.market.market_id == "synthetic-kalshi-market-id"


def test_kalshi_replay_requires_and_preserves_explicit_unified_price_context() -> None:
    events = [
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot_unified_yes.json",
            Venue.KALSHI,
            "kalshi/unified-replay-snapshot",
        ),
        _envelope(
            FIXTURES / "kalshi" / "orderbook_delta_unified_yes.json",
            Venue.KALSHI,
            "kalshi/unified-replay-delta",
        ),
    ]

    result = replay_events(
        events,
        kalshi_price_convention=KalshiPriceConvention.UNIFIED_YES_LEG,
    )

    assert result.final_state.price_convention is KalshiPriceConvention.UNIFIED_YES_LEG
    assert [level.price for level in result.final_state.derived_yes_asks().levels] == [
        Decimal("0.60"),
        Decimal("0.65"),
    ]


def test_kalshi_replay_rejects_unknown_price_context() -> None:
    snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/unknown-price-context",
    )
    with pytest.raises(ReplayError):
        replay_events([snapshot])


def test_non_monotonic_events_fail_closed_by_default() -> None:
    first = _envelope(
        FIXTURES / "polymarket" / "orderbook_snapshot.json",
        Venue.POLYMARKET,
        "polymarket/first",
    )
    second_payload = {
        "event_type": "book",
        "asset_id": "synthetic-polymarket-yes-token",
        "market": "0xsynthetic-polymarket-market",
        "bids": [],
        "asks": [],
        "timestamp": "1699999999000",
    }
    second = RawEnvelope.from_payload(
        venue=Venue.POLYMARKET,
        fixture=FixtureReference("polymarket/second", Venue.POLYMARKET),
        payload=second_payload,
        source_type=SourceType.FIXTURE_REST,
        endpoint_or_channel="fixture://snapshot",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
    )

    with pytest.raises(ReplayError):
        replay_events([first, second])


def test_non_monotonic_audit_replay_marks_state_invalid() -> None:
    first = _envelope(
        FIXTURES / "polymarket" / "orderbook_snapshot.json",
        Venue.POLYMARKET,
        "polymarket/audit-first",
    )
    second_payload = {
        "event_type": "book",
        "asset_id": "synthetic-polymarket-yes-token",
        "market": "0xsynthetic-polymarket-market",
        "bids": [],
        "asks": [],
        "timestamp": "1699999999000",
    }
    second = RawEnvelope.from_payload(
        venue=Venue.POLYMARKET,
        fixture=FixtureReference("polymarket/audit-second", Venue.POLYMARKET),
        payload=second_payload,
        source_type=SourceType.FIXTURE_REST,
        endpoint_or_channel="fixture://snapshot",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
    )

    result = replay_events([first, second], strict=False)

    assert result.validity is StateValidity.INVALID
    assert result.frames[1].validity is StateValidity.INVALID
    assert result.frames[1].state.order_book.validity is StateValidity.INVALID
    assert result.warnings[0].code.value == "non_monotonic_event"


def test_sequence_gap_fails_closed_by_default() -> None:
    snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/sequence-first",
    )
    delta_payload = {
        "type": "orderbook_delta",
        "sid": 7,
        "seq": 13,
        "msg": {
            "market_ticker": "SYNTHETIC-EVENT-MARKET",
            "market_id": "synthetic-kalshi-market-id",
            "price_dollars": "0.25",
            "delta_fp": "1.000",
            "side": "yes",
            "ts": "2023-11-14T22:13:21Z",
        },
    }
    delta = RawEnvelope.from_payload(
        venue=Venue.KALSHI,
        fixture=FixtureReference("kalshi/sequence-gap", Venue.KALSHI),
        payload=delta_payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
    )

    with pytest.raises(ReplayError):
        replay_events([snapshot, delta], kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG)


def test_sequence_gap_audit_replay_marks_state_invalid() -> None:
    snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/audit-sequence-first",
    )
    delta_payload = {
        "type": "orderbook_delta",
        "sid": 7,
        "seq": 13,
        "msg": {
            "market_ticker": "SYNTHETIC-EVENT-MARKET",
            "market_id": "synthetic-kalshi-market-id",
            "price_dollars": "0.25",
            "delta_fp": "1.000",
            "side": "yes",
            "ts": "2023-11-14T22:13:21Z",
        },
    }
    delta = RawEnvelope.from_payload(
        venue=Venue.KALSHI,
        fixture=FixtureReference("kalshi/audit-sequence-gap", Venue.KALSHI),
        payload=delta_payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
    )

    result = replay_events(
        [snapshot, delta],
        strict=False,
        kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )

    assert result.validity is StateValidity.INVALID
    assert result.frames[1].validity is StateValidity.INVALID
    assert result.frames[1].state.validity is StateValidity.INVALID
    assert result.warnings[0].code.value == "sequence_gap"


def test_fresh_snapshot_restores_audit_validity() -> None:
    snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/restore-first",
    )
    gap_payload = {
        "type": "orderbook_delta",
        "sid": 7,
        "seq": 13,
        "msg": {
            "market_ticker": "SYNTHETIC-EVENT-MARKET",
            "market_id": "synthetic-kalshi-market-id",
            "price_dollars": "0.25",
            "delta_fp": "1.000",
            "side": "yes",
            "ts": "2023-11-14T22:13:21Z",
        },
    }
    gap = RawEnvelope.from_payload(
        venue=Venue.KALSHI,
        fixture=FixtureReference("kalshi/restore-gap", Venue.KALSHI),
        payload=gap_payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
    )
    fresh = RawEnvelope.from_payload(
        venue=Venue.KALSHI,
        fixture=FixtureReference("kalshi/restore-fresh", Venue.KALSHI),
        payload={
            "type": "orderbook_snapshot",
            "sid": 7,
            "seq": 20,
            "msg": {
                "market_ticker": "SYNTHETIC-EVENT-MARKET",
                "market_id": "synthetic-kalshi-market-id",
                "yes_dollars_fp": [["0.25", "3.000"]],
                "no_dollars_fp": [["0.40", "6.000"]],
                "ts": "2023-11-14T22:13:22Z",
            },
        },
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
    )

    result = replay_events(
        [snapshot, gap, fresh],
        strict=False,
        kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )

    assert result.frames[1].validity is StateValidity.INVALID
    assert result.frames[2].validity is StateValidity.VALID
    assert result.validity is StateValidity.VALID


def test_multiple_updates_preserve_ordered_lineage() -> None:
    snapshot = _envelope(
        FIXTURES / "kalshi" / "orderbook_snapshot.json",
        Venue.KALSHI,
        "kalshi/lineage-snapshot",
    )
    first_delta = _envelope(
        FIXTURES / "kalshi" / "orderbook_delta.json",
        Venue.KALSHI,
        "kalshi/lineage-first-delta",
    )
    second_delta = RawEnvelope.from_payload(
        venue=Venue.KALSHI,
        fixture=FixtureReference("kalshi/lineage-second-delta", Venue.KALSHI),
        payload={
            "type": "orderbook_delta",
            "sid": 7,
            "seq": 12,
            "msg": {
                "market_ticker": "SYNTHETIC-EVENT-MARKET",
                "market_id": "synthetic-kalshi-market-id",
                "price_dollars": "0.25",
                "delta_fp": "1.000",
                "side": "yes",
                "ts": "2023-11-14T22:13:22Z",
            },
        },
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
    )

    result = replay_events(
        [snapshot, first_delta, second_delta],
        kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )

    assert result.final_state.raw_refs == (
        snapshot.raw_ref,
        first_delta.raw_ref,
        second_delta.raw_ref,
    )
    serialized_lineage = stable_json_bytes(result.final_state.raw_refs)
    assert serialized_lineage.index(snapshot.raw_ref.value.encode()) < serialized_lineage.index(
        first_delta.raw_ref.value.encode()
    )
    assert serialized_lineage.index(first_delta.raw_ref.value.encode()) < serialized_lineage.index(
        second_delta.raw_ref.value.encode()
    )


def test_duplicate_event_references_are_preserved_deterministically() -> None:
    snapshot = _envelope(
        FIXTURES / "polymarket" / "orderbook_snapshot.json",
        Venue.POLYMARKET,
        "polymarket/duplicate-snapshot",
    )
    update = _envelope(
        FIXTURES / "polymarket" / "price_change.json",
        Venue.POLYMARKET,
        "polymarket/duplicate-update",
    )

    result = replay_events([snapshot, update, update])

    assert result.final_state.raw_refs == (
        snapshot.raw_ref,
        update.raw_ref,
        update.raw_ref,
    )


def test_replay_requires_snapshot_before_update() -> None:
    delta = _envelope(
        FIXTURES / "kalshi" / "orderbook_delta.json",
        Venue.KALSHI,
        "kalshi/delta-only",
    )

    with pytest.raises(ReplayError):
        replay_events([delta], kalshi_price_convention=KalshiPriceConvention.OUTCOME_LEG)
