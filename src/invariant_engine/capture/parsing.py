"""Strict bounded parsing for captured venue-native order books."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import NoReturn, cast

from invariant_engine.capture.models import (
    CaptureTarget,
    KalshiOrderBook,
    PolymarketOrderBook,
    PriceLevel,
)
from invariant_engine.domain.ids import Venue

_GENERAL_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?", re.ASCII)
_KALSHI_QUANTITY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", re.ASCII)
_JSON_WHITESPACE = " \t\r\n"


class ParseFailure(StrEnum):
    UTF8_INVALID = "utf8_invalid"
    JSON_INVALID = "json_invalid"
    SCHEMA_INVALID = "schema_invalid"
    IDENTIFIER_MISMATCH = "identifier_mismatch"


@dataclass(frozen=True, slots=True)
class ParseResult:
    failure: ParseFailure | None
    order_book: PolymarketOrderBook | KalshiOrderBook | None


class _JsonViolation(ValueError):
    pass


class _SchemaViolation(ValueError):
    pass


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len(pairs) > 4_096:
        raise _JsonViolation("object member limit exceeded")
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _JsonViolation("duplicate object key")
        result[key] = value
    return result


def _numeric_token(value: str) -> Decimal:
    if len(value) > 64 or not value.isascii():
        raise _JsonViolation("numeric token limit exceeded")
    try:
        with localcontext(Context(prec=80)):
            return Decimal(value)
    except InvalidOperation as exc:
        raise _JsonViolation("invalid numeric token") from exc


def _constant(value: str) -> NoReturn:
    raise _JsonViolation("nonstandard numeric constant")


def _validate_json_tree(value: object, depth: int = 0) -> None:
    if isinstance(value, str):
        if len(value) > 262_144:
            raise _JsonViolation("decoded string limit exceeded")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _JsonViolation("unpaired Unicode surrogate") from exc
        return
    if type(value) is dict:
        if depth + 1 > 32 or len(value) > 4_096:
            raise _JsonViolation("container limit exceeded")
        for key, item in cast(dict[str, object], value).items():
            _validate_json_tree(key, depth + 1)
            _validate_json_tree(item, depth + 1)
        return
    if type(value) is list:
        if depth + 1 > 32 or len(value) > 10_000:
            raise _JsonViolation("container limit exceeded")
        for item in cast(list[object], value):
            _validate_json_tree(item, depth + 1)


def _decode(data: bytes) -> tuple[object | None, ParseFailure | None]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, ParseFailure.UTF8_INVALID
    try:
        decoder = json.JSONDecoder(
            object_pairs_hook=_pairs,
            parse_int=_numeric_token,
            parse_float=_numeric_token,
            parse_constant=_constant,
        )
        start = len(text) - len(text.lstrip(_JSON_WHITESPACE))
        value, end = decoder.raw_decode(text, start)
        if text[end:].strip(_JSON_WHITESPACE):
            raise _JsonViolation("trailing JSON content")
        _validate_json_tree(value)
    except (json.JSONDecodeError, _JsonViolation, RecursionError):
        return None, ParseFailure.JSON_INVALID
    if type(value) is not dict:
        return None, ParseFailure.JSON_INVALID
    return value, None


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise _SchemaViolation
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    if type(value) is not list:
        raise _SchemaViolation
    return cast(list[object], value)


def _string(value: object) -> str:
    if type(value) is not str:
        raise _SchemaViolation
    return value


def _decimal(value: object, grammar: re.Pattern[str] = _GENERAL_DECIMAL) -> tuple[str, Decimal]:
    text = _string(value)
    if len(text) > 64 or grammar.fullmatch(text) is None:
        raise _SchemaViolation
    try:
        with localcontext(Context(prec=80)):
            parsed = Decimal(text)
    except InvalidOperation as exc:
        raise _SchemaViolation from exc
    if not parsed.is_finite():
        raise _SchemaViolation
    return text, parsed


def _polymarket_levels(value: object, *, ascending: bool) -> tuple[PriceLevel, ...]:
    levels: list[PriceLevel] = []
    previous: Decimal | None = None
    for raw_level in _array(value):
        level = _object(raw_level)
        if "price" not in level or "size" not in level:
            raise _SchemaViolation
        price_text, price = _decimal(level["price"])
        size_text, size = _decimal(level["size"])
        if previous is not None and (
            (ascending and price < previous) or (not ascending and price > previous)
        ):
            raise _SchemaViolation
        previous = price
        levels.append(PriceLevel(price_text, size_text, price, size))
    return tuple(levels)


def _kalshi_levels(value: object) -> tuple[PriceLevel, ...]:
    levels: list[PriceLevel] = []
    for raw_level in _array(value):
        pair = _array(raw_level)
        if len(pair) != 2:
            raise _SchemaViolation
        price_text, price = _decimal(pair[0])
        quantity_text, quantity = _decimal(pair[1], _KALSHI_QUANTITY)
        levels.append(PriceLevel(price_text, quantity_text, price, quantity))
    return tuple(levels)


def parse_order_book(target: CaptureTarget, data: bytes) -> ParseResult:
    payload, failure = _decode(data)
    if failure is not None:
        return ParseResult(failure, None)
    try:
        record = _object(payload)
        if target.venue is Venue.POLYMARKET:
            required = {
                "market",
                "asset_id",
                "timestamp",
                "hash",
                "bids",
                "asks",
                "min_order_size",
                "tick_size",
                "neg_risk",
                "last_trade_price",
            }
            if not required.issubset(record):
                raise _SchemaViolation
            market = _string(record["market"])
            asset_id = _string(record["asset_id"])
            timestamp = _string(record["timestamp"])
            book_hash = _string(record["hash"])
            bids = _polymarket_levels(record["bids"], ascending=False)
            asks = _polymarket_levels(record["asks"], ascending=True)
            min_text, min_value = _decimal(record["min_order_size"])
            tick_text, tick_value = _decimal(record["tick_size"])
            if type(record["neg_risk"]) is not bool:
                raise _SchemaViolation
            last_text, last_value = _decimal(record["last_trade_price"])
            if asset_id != target.identifier:
                return ParseResult(ParseFailure.IDENTIFIER_MISMATCH, None)
            return ParseResult(
                None,
                PolymarketOrderBook(
                    market,
                    asset_id,
                    timestamp,
                    book_hash,
                    bids,
                    asks,
                    min_text,
                    min_value,
                    tick_text,
                    tick_value,
                    record["neg_risk"],
                    last_text,
                    last_value,
                ),
            )
        if "orderbook_fp" not in record:
            raise _SchemaViolation
        orderbook = _object(record["orderbook_fp"])
        if "yes_dollars" not in orderbook or "no_dollars" not in orderbook:
            raise _SchemaViolation
        return ParseResult(
            None,
            KalshiOrderBook(
                ticker=target.identifier,
                yes_dollars=_kalshi_levels(orderbook["yes_dollars"]),
                no_dollars=_kalshi_levels(orderbook["no_dollars"]),
            ),
        )
    except _SchemaViolation:
        return ParseResult(ParseFailure.SCHEMA_INVALID, None)


__all__ = ["ParseFailure", "ParseResult", "parse_order_book"]
