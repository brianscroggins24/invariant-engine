from __future__ import annotations

from conftest import kalshi_body, kalshi_target, polymarket_body, polymarket_target
from invariant_engine.capture import (
    KalshiOrderBook,
    ParseFailure,
    PolymarketOrderBook,
    parse_order_book,
)


def test_polymarket_preserves_order_duplicates_strings_and_decimals() -> None:
    result = parse_order_book(polymarket_target(), polymarket_body())
    assert result.failure is None
    assert isinstance(result.order_book, PolymarketOrderBook)
    assert [level.price_text for level in result.order_book.bids] == ["0.50", "0.50"]
    assert result.order_book.bids[0].price.as_tuple() == result.order_book.bids[1].price.as_tuple()
    assert result.order_book.timestamp == "opaque"


def test_kalshi_preserves_native_sides_and_empty_arrays() -> None:
    result = parse_order_book(kalshi_target(), kalshi_body())
    assert isinstance(result.order_book, KalshiOrderBook)
    assert len(result.order_book.yes_dollars) == 2
    empty = parse_order_book(
        kalshi_target(), b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}}'
    )
    assert isinstance(empty.order_book, KalshiOrderBook)
    assert empty.order_book.yes_dollars == ()


def test_utf8_json_and_identifier_failures_are_distinct() -> None:
    assert parse_order_book(polymarket_target(), b"\xff").failure is ParseFailure.UTF8_INVALID
    assert parse_order_book(polymarket_target(), b"{}").failure is ParseFailure.SCHEMA_INVALID
    assert (
        parse_order_book(polymarket_target(), polymarket_body("456")).failure
        is ParseFailure.IDENTIFIER_MISMATCH
    )


def test_duplicate_keys_at_nested_depth_and_constants_reject() -> None:
    duplicate = b'{"orderbook_fp":{"yes_dollars":[],"yes_dollars":[],"no_dollars":[]}}'
    assert parse_order_book(kalshi_target(), duplicate).failure is ParseFailure.JSON_INVALID
    assert parse_order_book(kalshi_target(), b'{"x":NaN}').failure is ParseFailure.JSON_INVALID


def test_unpaired_surrogate_depth_array_member_and_string_limits_reject() -> None:
    cases = [
        b'{"x":"\\ud800"}',
        ("[" * 33 + "0" + "]" * 33).encode(),
        ("[" + ",".join("0" for _ in range(10_001)) + "]").encode(),
        ('{"x":"' + "a" * 262_145 + '"}').encode(),
    ]
    for case in cases:
        assert parse_order_book(kalshi_target(), case).failure is ParseFailure.JSON_INVALID


def test_numeric_grammar_exact_types_and_ordering_reject() -> None:
    assert (
        parse_order_book(
            kalshi_target(),
            b'{"orderbook_fp":{"yes_dollars":[[".4","2.00"]],"no_dollars":[]}}',
        ).failure
        is ParseFailure.SCHEMA_INVALID
    )
    assert (
        parse_order_book(
            kalshi_target(),
            b'{"orderbook_fp":{"yes_dollars":[["0.4",2]],"no_dollars":[]}}',
        ).failure
        is ParseFailure.SCHEMA_INVALID
    )
    unordered = polymarket_body().replace(
        b'{"price":"0.50","size":"2.0"},{"price":"0.50","size":"1.0"}',
        b'{"price":"0.40","size":"2.0"},{"price":"0.50","size":"1.0"}',
    )
    assert parse_order_book(polymarket_target(), unordered).failure is ParseFailure.SCHEMA_INVALID


def test_binary_float_is_never_used_for_unknown_json_numbers() -> None:
    body = polymarket_body()[:-1] + b',"unknown":0.12345678901234567890123456789}'
    assert isinstance(parse_order_book(polymarket_target(), body).order_book, PolymarketOrderBook)


def test_json_numeric_token_and_kalshi_quantity_grammar_limits() -> None:
    numeric = ('{"unknown":' + "1" * 65 + "}").encode()
    assert parse_order_book(kalshi_target(), numeric).failure is ParseFailure.JSON_INVALID
    quantity = b'{"orderbook_fp":{"yes_dollars":[["0.4","2.0"]],"no_dollars":[]}}'
    assert parse_order_book(kalshi_target(), quantity).failure is ParseFailure.SCHEMA_INVALID


def test_level_structures_require_exact_shapes() -> None:
    kalshi = b'{"orderbook_fp":{"yes_dollars":[["0.4","2.00","x"]],"no_dollars":[]}}'
    polymarket = polymarket_body().replace(b'"size":"2.0"', b'"size":true', 1)
    assert parse_order_book(kalshi_target(), kalshi).failure is ParseFailure.SCHEMA_INVALID
    assert parse_order_book(polymarket_target(), polymarket).failure is ParseFailure.SCHEMA_INVALID
