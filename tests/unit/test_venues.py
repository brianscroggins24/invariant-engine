from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invariant_engine.domain.errors import DomainError, PayloadError
from invariant_engine.domain.ids import (
    ContractReference,
    FixtureReference,
    MarketReference,
    RawReference,
    Venue,
)
from invariant_engine.domain.order_book import BookSide, BookSideKind, OrderBookSnapshot
from invariant_engine.provenance import RawEnvelope, SourceType
from invariant_engine.serialization import stable_json_text
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiMarketIdentity,
    KalshiNativeSideKind,
    KalshiOrderBookDelta,
    KalshiPriceConvention,
)
from invariant_engine.venues.kalshi import (
    apply_delta as apply_kalshi_delta,
)
from invariant_engine.venues.kalshi import (
    parse_delta as parse_kalshi_delta,
)
from invariant_engine.venues.kalshi import (
    parse_snapshot as parse_kalshi_snapshot,
)
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
    apply_price_change,
)
from invariant_engine.venues.polymarket import (
    parse_snapshot as parse_polymarket_snapshot,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
UTC_CAPTURE = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def _envelope(path: Path, venue: Venue, name: str) -> RawEnvelope:
    schema = (
        POLYMARKET_DIRECT_SCHEMA_VERSION
        if venue is Venue.POLYMARKET
        else KALSHI_ORDERBOOK_SCHEMA_VERSION
    )
    return RawEnvelope.from_fixture_bytes(
        venue=venue,
        fixture=FixtureReference(name, venue),
        data=path.read_bytes(),
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://orderbook",
        capture_timestamp=UTC_CAPTURE,
        schema_version=schema,
    )


def _payload_envelope(
    *, venue: Venue, fixture: str, payload: dict[str, object], schema: str | None = None
) -> RawEnvelope:
    return RawEnvelope.from_payload(
        venue=venue,
        fixture=FixtureReference(fixture, venue),
        payload=payload,
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://market-data",
        capture_timestamp=UTC_CAPTURE,
        schema_version=schema
        or (
            POLYMARKET_DIRECT_SCHEMA_VERSION
            if venue is Venue.POLYMARKET
            else KALSHI_ORDERBOOK_SCHEMA_VERSION
        ),
    )


def _kalshi_delta_payload(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "market_ticker": "SYNTHETIC-EVENT-MARKET",
        "market_id": "synthetic-kalshi-market-id",
        "price_dollars": "0.25",
        "delta_fp": "1.000",
        "side": "yes",
        "ts": "2023-11-14T22:13:21Z",
    }
    message.update(overrides.pop("msg", {}))  # type: ignore[arg-type]
    payload: dict[str, object] = {"type": "orderbook_delta", "sid": 7, "seq": 11, "msg": message}
    payload.update(overrides)
    return payload


def _kalshi_snapshot_payload(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "market_ticker": "SYNTHETIC-EVENT-MARKET",
        "market_id": "synthetic-kalshi-market-id",
        "yes_dollars_fp": [["0.20", "10.000"]],
        "no_dollars_fp": [["0.35", "4.000"]],
    }
    message.update(overrides.pop("msg", {}))  # type: ignore[arg-type]
    payload: dict[str, object] = {"type": "orderbook_snapshot", "sid": 7, "seq": 10, "msg": message}
    payload.update(overrides)
    return payload


def test_polymarket_keeps_direct_bids_and_asks_and_optional_fields() -> None:
    parsed = parse_polymarket_snapshot(
        _envelope(
            FIXTURES / "polymarket" / "orderbook_snapshot.json",
            Venue.POLYMARKET,
            "polymarket/orderbook_snapshot.json",
        )
    )

    assert parsed.order_book.bids.levels[0].size == Decimal("12.000")
    assert [level.price for level in parsed.order_book.asks.levels] == [
        Decimal("0.55"),
        Decimal("0.60"),
    ]
    assert parsed.book_hash == "synthetic-polymarket-book-hash"
    assert parsed.minimum_order_size == Decimal("1.000")
    assert parsed.tick_size == Decimal("0.010")
    assert parsed.negative_risk is False
    assert parsed.schema_version == POLYMARKET_DIRECT_SCHEMA_VERSION
    assert parsed.raw_ref is not None


def test_kalshi_outcome_leg_preserves_native_sides_and_derives_complements() -> None:
    parsed = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            "kalshi/orderbook_snapshot.json",
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )

    assert parsed.yes_side.kind is KalshiNativeSideKind.YES
    assert parsed.no_side.kind is KalshiNativeSideKind.NO
    assert parsed.market.market_ticker == "SYNTHETIC-EVENT-MARKET"
    assert parsed.market.market_id == "synthetic-kalshi-market-id"
    assert parsed.yes_side.levels[0].price == Decimal("0.25")
    assert parsed.interpreted_yes_bids().kind is BookSideKind.YES_BID
    assert parsed.interpreted_no_bids().kind is BookSideKind.NO_BID
    assert [level.price for level in parsed.derived_yes_asks().levels] == [
        Decimal("0.60"),
        Decimal("0.65"),
    ]
    assert [level.price for level in parsed.derived_no_asks().levels] == [
        Decimal("0.75"),
        Decimal("0.80"),
    ]
    assert parsed.derived_yes_asks().warnings[-1].code.value == "derived_value"
    assert parsed.warnings[-1].code.value == "unavailable_field"


def test_kalshi_unified_yes_leg_does_not_complement_no_side_as_yes_asks() -> None:
    parsed = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot_unified_yes.json",
            Venue.KALSHI,
            "kalshi/unified-orderbook_snapshot.json",
        ),
        price_convention=KalshiPriceConvention.UNIFIED_YES_LEG,
    )

    assert [level.price for level in parsed.derived_yes_asks().levels] == [
        Decimal("0.60"),
        Decimal("0.65"),
    ]
    assert [level.price for level in parsed.interpreted_no_bids().levels] == [
        Decimal("0.40"),
        Decimal("0.35"),
    ]
    assert parsed.price_convention is KalshiPriceConvention.UNIFIED_YES_LEG
    serialized_native_no = stable_json_text(parsed.no_side)
    assert '"kind":"no"' in serialized_native_no
    assert "no_bid" not in serialized_native_no


def test_missing_optional_polymarket_fields_remain_none() -> None:
    envelope = _payload_envelope(
        venue=Venue.POLYMARKET,
        fixture="minimal-polymarket",
        payload={
            "event_type": "book",
            "asset_id": "asset",
            "market": "market",
            "timestamp": "1700000000000",
            "bids": [],
            "asks": [],
        },
    )
    parsed = parse_polymarket_snapshot(envelope)

    assert parsed.book_hash is None
    assert parsed.minimum_order_size is None
    assert parsed.tick_size is None
    assert parsed.negative_risk is None
    assert parsed.last_trade_price is None


def test_historical_polymarket_parser_rejects_polymarket_us_material() -> None:
    envelope = RawEnvelope.from_payload(
        venue=Venue.POLYMARKET_US,
        fixture=FixtureReference("synthetic-us-book", Venue.POLYMARKET_US),
        payload={
            "event_type": "book",
            "asset_id": "synthetic-asset",
            "market": "synthetic-market",
            "timestamp": "1700000000000",
            "bids": [],
            "asks": [],
        },
        source_type=SourceType.FIXTURE_WEBSOCKET,
        endpoint_or_channel="fixture://polymarket-us",
        capture_timestamp=UTC_CAPTURE,
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
    )
    with pytest.raises(PayloadError, match="non-Polymarket"):
        parse_polymarket_snapshot(envelope)


def test_incomplete_payloads_are_rejected() -> None:
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(
            _envelope(
                FIXTURES / "polymarket" / "incomplete_snapshot.json",
                Venue.POLYMARKET,
                "polymarket/incomplete_snapshot.json",
            )
        )
    with pytest.raises(PayloadError):
        parse_kalshi_snapshot(
            _envelope(
                FIXTURES / "kalshi" / "incomplete_snapshot.json",
                Venue.KALSHI,
                "kalshi/incomplete_snapshot.json",
            ),
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
        )


def test_polymarket_batch_validates_all_entries_then_ignores_other_tokens() -> None:
    snapshot_envelope = _envelope(
        FIXTURES / "polymarket" / "orderbook_snapshot.json",
        Venue.POLYMARKET,
        "polymarket/batch-snapshot",
    )
    snapshot = parse_polymarket_snapshot(snapshot_envelope)
    batch = _payload_envelope(
        venue=Venue.POLYMARKET,
        fixture="polymarket/batch-update",
        payload={
            "event_type": "price_change",
            "market": "0xsynthetic-polymarket-market",
            "price_changes": [
                {
                    "asset_id": "synthetic-polymarket-yes-token",
                    "price": "0.50",
                    "size": "6.000",
                    "side": "BUY",
                    "hash": "matching-change-hash",
                },
                {
                    "asset_id": "another-token",
                    "price": "0.55",
                    "size": "99.000",
                    "side": "SELL",
                    "hash": "unrelated-change-hash",
                },
            ],
            "timestamp": "1700000001000",
        },
    )

    updated = apply_price_change(snapshot, batch)

    assert updated.order_book.bids.levels[0].size == Decimal("6.000")
    assert updated.raw_refs == (snapshot_envelope.raw_ref, batch.raw_ref)
    assert updated.order_book.warnings[-1].code.value == "ignored_event_entry"


@pytest.mark.parametrize("field", ["market", "asset_id"])
def test_polymarket_ids_are_required_non_empty_strings(field: str) -> None:
    payload: dict[str, object] = {
        "event_type": "book",
        "asset_id": "asset",
        "market": "market",
        "timestamp": "1700000000000",
        "bids": [],
        "asks": [],
    }
    payload[field] = 123
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(
            _payload_envelope(venue=Venue.POLYMARKET, fixture=field, payload=payload)
        )


def test_polymarket_timestamp_and_schema_are_required() -> None:
    payload: dict[str, object] = {
        "event_type": "book",
        "asset_id": "asset",
        "market": "market",
        "bids": [],
        "asks": [],
    }
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(
            _payload_envelope(venue=Venue.POLYMARKET, fixture="missing-time", payload=payload)
        )
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(
            _payload_envelope(
                venue=Venue.POLYMARKET,
                fixture="wrong-schema",
                payload={**payload, "timestamp": "1700000000000"},
                schema="polymarket-sdk-wrapper-v1",
            )
        )
    missing_schema = RawEnvelope.from_payload(
        venue=Venue.POLYMARKET,
        fixture=FixtureReference("missing-schema", Venue.POLYMARKET),
        payload={**payload, "timestamp": "1700000000000"},
        source_type=SourceType.FIXTURE_REST,
        endpoint_or_channel="fixture://snapshot",
        capture_timestamp=UTC_CAPTURE,
    )
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(missing_schema)


def test_polymarket_optional_types_and_change_hashes_are_validated() -> None:
    payload: dict[str, object] = {
        "event_type": "book",
        "asset_id": "asset",
        "market": "market",
        "timestamp": "1700000000000",
        "bids": [],
        "asks": [],
        "neg_risk": "false",
    }
    with pytest.raises(PayloadError):
        parse_polymarket_snapshot(
            _payload_envelope(venue=Venue.POLYMARKET, fixture="bad-optional", payload=payload)
        )

    snapshot = parse_polymarket_snapshot(
        _envelope(
            FIXTURES / "polymarket" / "orderbook_snapshot.json",
            Venue.POLYMARKET,
            "polymarket/change-validation",
        )
    )
    bad_change = _payload_envelope(
        venue=Venue.POLYMARKET,
        fixture="bad-change",
        payload={
            "event_type": "price_change",
            "market": snapshot.market.value,
            "timestamp": "1700000001000",
            "price_changes": [
                {
                    "asset_id": "other-token",
                    "price": "0.50",
                    "size": "1.000",
                    "side": "BUY",
                }
            ],
        },
    )
    with pytest.raises(PayloadError):
        apply_price_change(snapshot, bad_change)


def test_kalshi_delta_session_must_match_snapshot() -> None:
    snapshot = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            "kalshi/session-snapshot",
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    mismatched = _payload_envelope(
        venue=Venue.KALSHI,
        fixture="kalshi/session-mismatch",
        payload=_kalshi_delta_payload(sid=8),
    )

    delta = parse_kalshi_delta(mismatched, price_convention=KalshiPriceConvention.OUTCOME_LEG)

    assert delta.session_id == 8
    with pytest.raises(PayloadError):
        apply_kalshi_delta(snapshot, delta)


def _direct_kalshi_delta(**overrides: object) -> KalshiOrderBookDelta:
    values: dict[str, object] = {
        "market": KalshiMarketIdentity("ticker", "market-id"),
        "schema_version": KALSHI_ORDERBOOK_SCHEMA_VERSION,
        "timestamp": UTC_CAPTURE,
        "timestamp_source": "venue",
        "sequence": 11,
        "session_id": 7,
        "price_convention": KalshiPriceConvention.OUTCOME_LEG,
        "side": KalshiNativeSideKind.YES,
        "price": "0.25",
        "delta_size": "-1.000",
        "raw_ref": RawReference("raw", Venue.KALSHI),
        "warnings": (),
    }
    values.update(overrides)
    return KalshiOrderBookDelta(**values)  # type: ignore[arg-type]


def test_kalshi_delta_direct_construction_rejects_cross_venue_provenance() -> None:
    with pytest.raises(DomainError):
        _direct_kalshi_delta(raw_ref=RawReference("raw", Venue.POLYMARKET))


@pytest.mark.parametrize("price", [0.25, Decimal("NaN"), Decimal("Infinity"), "1.01"])
def test_kalshi_delta_direct_price_uses_decimal_policy(price: object) -> None:
    with pytest.raises(DomainError):
        _direct_kalshi_delta(price=price)


@pytest.mark.parametrize("delta_size", [0.5, Decimal("NaN"), Decimal("Infinity")])
def test_kalshi_delta_direct_size_rejects_invalid_values(delta_size: object) -> None:
    with pytest.raises(DomainError):
        _direct_kalshi_delta(delta_size=delta_size)


def test_kalshi_delta_direct_size_allows_negative_decimal_and_normalizes_fields() -> None:
    delta = _direct_kalshi_delta(price="0.2500", delta_size="-1.000")

    assert delta.price == Decimal("0.2500")
    assert delta.delta_size == Decimal("-1.000")
    assert delta.timestamp_source.value == "venue"


def test_kalshi_delta_direct_construction_validates_timestamp_source() -> None:
    with pytest.raises(DomainError):
        _direct_kalshi_delta(timestamp_source="unknown")
    with pytest.raises(DomainError):
        _direct_kalshi_delta(timestamp_source="venue", timestamp=datetime(2023, 11, 14, 22))


def test_polymarket_wrapper_direct_construction_validates_underlying_book_and_options() -> None:
    parsed = parse_polymarket_snapshot(
        _envelope(
            FIXTURES / "polymarket" / "orderbook_snapshot.json",
            Venue.POLYMARKET,
            "polymarket/direct-invariants",
        )
    )
    with pytest.raises(DomainError):
        replace(parsed, order_book=replace(parsed.order_book, contract=None))
    with pytest.raises(DomainError):
        replace(parsed, minimum_order_size=0.5)
    with pytest.raises(DomainError):
        replace(parsed, tick_size=1.1)
    with pytest.raises(DomainError):
        replace(parsed, last_trade_price=Decimal("NaN"))
    with pytest.raises(DomainError):
        replace(parsed, negative_risk="false")
    with pytest.raises(DomainError):
        replace(parsed, book_hash=123)

    kalshi_book = OrderBookSnapshot(
        venue=Venue.KALSHI,
        market=MarketReference("kalshi-market", Venue.KALSHI),
        contract=ContractReference("kalshi-contract", Venue.KALSHI),
        timestamp=UTC_CAPTURE,
        bids=BookSide.normalized(BookSideKind.BID, []),
        asks=BookSide.normalized(BookSideKind.ASK, []),
        raw_ref=RawReference("raw", Venue.KALSHI),
        raw_refs=(RawReference("raw", Venue.KALSHI),),
        warnings=(),
    )
    with pytest.raises(DomainError):
        replace(parsed, order_book=kalshi_book)


def test_kalshi_price_convention_must_match_snapshot() -> None:
    snapshot = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            "kalshi/convention-snapshot",
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    delta = parse_kalshi_delta(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_delta_unified_yes.json",
            Venue.KALSHI,
            "kalshi/convention-delta",
        ),
        price_convention=KalshiPriceConvention.UNIFIED_YES_LEG,
    )
    with pytest.raises(PayloadError):
        apply_kalshi_delta(snapshot, delta)


def test_kalshi_delta_sequence_must_be_contiguous_when_applied_directly() -> None:
    snapshot = parse_kalshi_snapshot(
        _envelope(
            FIXTURES / "kalshi" / "orderbook_snapshot.json",
            Venue.KALSHI,
            "kalshi/sequence-snapshot",
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    delta = parse_kalshi_delta(
        _payload_envelope(
            venue=Venue.KALSHI,
            fixture="kalshi/direct-sequence-gap",
            payload=_kalshi_delta_payload(seq=13),
        ),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    with pytest.raises(PayloadError):
        apply_kalshi_delta(snapshot, delta)


def test_kalshi_required_metadata_rejects_missing_invalid_and_boolean_values() -> None:
    for field in ("sid", "seq"):
        payload = _kalshi_snapshot_payload()
        payload.pop(field)
        with pytest.raises(PayloadError):
            parse_kalshi_snapshot(
                _payload_envelope(venue=Venue.KALSHI, fixture=f"missing-{field}", payload=payload),
                price_convention=KalshiPriceConvention.OUTCOME_LEG,
            )
    for field in ("sid", "seq"):
        payload = _kalshi_snapshot_payload(**{field: True})
        with pytest.raises(PayloadError):
            parse_kalshi_snapshot(
                _payload_envelope(venue=Venue.KALSHI, fixture=f"boolean-{field}", payload=payload),
                price_convention=KalshiPriceConvention.OUTCOME_LEG,
            )
    payload = _kalshi_snapshot_payload(msg={"market_id": ""})
    with pytest.raises(PayloadError):
        parse_kalshi_snapshot(
            _payload_envelope(venue=Venue.KALSHI, fixture="missing-market-id", payload=payload),
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
        )


@pytest.mark.parametrize("field", ["sid", "seq"])
def test_kalshi_delta_requires_session_and_sequence(field: str) -> None:
    payload = _kalshi_delta_payload()
    payload.pop(field)
    with pytest.raises(PayloadError):
        parse_kalshi_delta(
            _payload_envelope(
                venue=Venue.KALSHI, fixture=f"delta-missing-{field}", payload=payload
            ),
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
        )


@pytest.mark.parametrize("field", ["sid", "seq"])
def test_kalshi_delta_rejects_non_integer_or_non_positive_metadata(field: str) -> None:
    for value in (True, "11", 0):
        payload = _kalshi_delta_payload(**{field: value})
        with pytest.raises(PayloadError):
            parse_kalshi_delta(
                _payload_envelope(
                    venue=Venue.KALSHI,
                    fixture=f"delta-invalid-{field}-{value}",
                    payload=payload,
                ),
                price_convention=KalshiPriceConvention.OUTCOME_LEG,
            )


def test_kalshi_market_ticker_must_be_non_empty() -> None:
    payload = _kalshi_snapshot_payload(msg={"market_ticker": ""})
    with pytest.raises(PayloadError):
        parse_kalshi_snapshot(
            _payload_envelope(venue=Venue.KALSHI, fixture="empty-market-ticker", payload=payload),
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
        )


@pytest.mark.parametrize("side_field", ["yes_dollars_fp", "no_dollars_fp"])
def test_kalshi_absent_native_side_is_an_empty_book(side_field: str) -> None:
    payload = _kalshi_snapshot_payload()
    message = payload["msg"]
    assert isinstance(message, dict)
    message.pop(side_field)
    parsed = parse_kalshi_snapshot(
        _payload_envelope(venue=Venue.KALSHI, fixture=f"absent-{side_field}", payload=payload),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    side = parsed.yes_side if side_field.startswith("yes") else parsed.no_side
    assert side.levels == ()


def test_kalshi_both_native_sides_may_be_empty() -> None:
    payload = _kalshi_snapshot_payload()
    message = payload["msg"]
    assert isinstance(message, dict)
    message.pop("yes_dollars_fp")
    message.pop("no_dollars_fp")
    parsed = parse_kalshi_snapshot(
        _payload_envelope(venue=Venue.KALSHI, fixture="empty-both", payload=payload),
        price_convention=KalshiPriceConvention.OUTCOME_LEG,
    )
    assert parsed.yes_side.levels == ()
    assert parsed.no_side.levels == ()


def test_kalshi_present_but_malformed_side_is_rejected() -> None:
    payload = _kalshi_snapshot_payload()
    message = payload["msg"]
    assert isinstance(message, dict)
    message["yes_dollars_fp"] = {"bad": "shape"}
    with pytest.raises(PayloadError):
        parse_kalshi_snapshot(
            _payload_envelope(venue=Venue.KALSHI, fixture="malformed-side", payload=payload),
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
        )


def test_direct_kalshi_native_side_invariants_are_enforced() -> None:
    from invariant_engine.venues.kalshi import KalshiMarketIdentity, KalshiOrderBookSnapshot

    with pytest.raises(DomainError):
        KalshiOrderBookSnapshot(
            venue=Venue.KALSHI,
            market=KalshiMarketIdentity("ticker", "market-id"),
            schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
            timestamp=UTC_CAPTURE,
            timestamp_source="venue",
            yes_side=BookSide(BookSideKind.BID, ()),
            no_side=BookSide(BookSideKind.NO_BID, ()),
            session_id=1,
            sequence=1,
            price_convention=KalshiPriceConvention.OUTCOME_LEG,
            raw_ref=RawReference("sha256:" + "0" * 64, Venue.KALSHI),
            raw_refs=(RawReference("sha256:" + "0" * 64, Venue.KALSHI),),
            warnings=(),
        )
