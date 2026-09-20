from decimal import Decimal

import pytest

from invariant_engine.domain.decimal_policy import parse_decimal, parse_price
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, Venue
from invariant_engine.domain.order_book import BookSide, BookSideKind, PriceLevel
from invariant_engine.serialization import stable_json_text


def test_typed_identifiers_retain_venue_and_entity_type() -> None:
    polymarket_market = MarketReference("same-value", Venue.POLYMARKET)
    kalshi_market = MarketReference("same-value", Venue.KALSHI)
    contract = ContractReference("same-value", Venue.POLYMARKET)

    assert polymarket_market != kalshi_market
    assert polymarket_market != contract
    assert polymarket_market.venue is Venue.POLYMARKET


def test_polymarket_us_is_distinct_from_international_polymarket() -> None:
    international = MarketReference("same-value", Venue.POLYMARKET)
    united_states = MarketReference("same-value", Venue.POLYMARKET_US)
    assert international != united_states
    assert Venue.POLYMARKET.value == "polymarket"
    assert Venue.POLYMARKET_US.value == "polymarket_us"


def test_decimal_policy_rejects_binary_float_and_preserves_scale() -> None:
    with pytest.raises(DomainError):
        parse_decimal(0.5, field="price")

    value = parse_price("0.5000")
    assert value == Decimal("0.5000")
    assert str(value) == "0.5000"
    assert '"0.5000"' in stable_json_text(value)


def test_price_range_and_negative_size_are_rejected() -> None:
    with pytest.raises(DomainError):
        parse_price("1.01")
    with pytest.raises(DomainError):
        PriceLevel("0.50", "-1")


def test_duplicate_levels_aggregate_and_zero_levels_are_removed() -> None:
    side = BookSide.normalized(
        BookSideKind.BID,
        [
            PriceLevel("0.50", "2.00"),
            PriceLevel("0.50", "3.000"),
            PriceLevel("0.40", "0"),
        ],
    )

    assert [(level.price, level.size) for level in side.levels] == [
        (Decimal("0.50"), Decimal("5.000"))
    ]
