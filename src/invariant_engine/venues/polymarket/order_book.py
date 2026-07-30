"""Polymarket direct market-stream fixture schema models and parsers.

Only the explicitly versioned direct event shape is supported here.  SDK
wrapper events are intentionally outside this Milestone 1 parser boundary.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from invariant_engine.domain.decimal_policy import parse_price, parse_quantity
from invariant_engine.domain.errors import DomainError, PayloadError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.domain.order_book import BookSide, BookSideKind, OrderBookSnapshot, PriceLevel
from invariant_engine.domain.time import parse_timestamp
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.provenance.raw_envelope import RawEnvelope

POLYMARKET_DIRECT_SCHEMA_VERSION = "polymarket-direct-v1"


def _required(payload: Mapping[str, Any], field: str) -> Any:
    if field not in payload:
        raise PayloadError(f"Polymarket payload is missing {field}")
    return payload[field]


def _required_non_empty_string(payload: Mapping[str, Any], field: str) -> str:
    value = _required(payload, field)
    if not isinstance(value, str) or not value.strip():
        raise PayloadError(f"Polymarket {field} must be a non-empty string")
    return value


def _schema(envelope: RawEnvelope) -> None:
    if envelope.schema_version != POLYMARKET_DIRECT_SCHEMA_VERSION:
        raise PayloadError(
            f"Polymarket parser requires schema_version {POLYMARKET_DIRECT_SCHEMA_VERSION!r}"
        )


def _levels(value: Any, *, field: str) -> list[PriceLevel]:
    if not isinstance(value, (list, tuple)):
        raise PayloadError(f"Polymarket {field} must be a list")
    result: list[PriceLevel] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise PayloadError(f"Polymarket {field}[{index}] must be an object")
        if "price" not in item or "size" not in item:
            raise PayloadError(f"Polymarket {field}[{index}] requires price and size")
        try:
            result.append(PriceLevel(item["price"], item["size"]))
        except DomainError as exc:
            raise PayloadError(f"Polymarket {field}[{index}] is malformed") from exc
    return result


def _optional_quantity(payload: Mapping[str, Any], *fields: str) -> Decimal | None:
    result: Decimal | None = None
    for field in fields:
        if field in payload and payload[field] is not None:
            try:
                parsed = parse_quantity(payload[field], field=field)
            except DomainError as exc:
                raise PayloadError(f"Polymarket {field} is malformed") from exc
            if result is None:
                result = parsed
    return result


def _optional_price(payload: Mapping[str, Any], *fields: str) -> Decimal | None:
    result: Decimal | None = None
    for field in fields:
        if field in payload and payload[field] is not None:
            try:
                parsed = parse_price(payload[field], field=field)
            except DomainError as exc:
                raise PayloadError(f"Polymarket {field} is malformed") from exc
            if result is None:
                result = parsed
    return result


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        raise PayloadError(f"Polymarket {field} must be a non-empty string when present")
    return value


@dataclass(frozen=True, slots=True)
class PolymarketOrderBookSnapshot:
    order_book: OrderBookSnapshot
    schema_version: str
    book_hash: str | None
    minimum_order_size: Decimal | None
    tick_size: Decimal | None
    negative_risk: bool | None
    last_trade_price: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.order_book, OrderBookSnapshot):
            raise DomainError("Polymarket snapshot order_book must be an OrderBookSnapshot")
        if self.order_book.venue is not Venue.POLYMARKET:
            raise DomainError("Polymarket snapshot requires a Polymarket order book")
        if not isinstance(self.order_book.contract, ContractReference):
            raise DomainError("Polymarket snapshot requires a contract or token reference")
        if self.order_book.contract.venue is not Venue.POLYMARKET:
            raise DomainError("Polymarket contract reference must belong to Polymarket")
        if not isinstance(self.schema_version, str) or (
            self.schema_version != POLYMARKET_DIRECT_SCHEMA_VERSION
        ):
            raise DomainError("unsupported Polymarket schema version")
        if self.book_hash is not None and (
            not isinstance(self.book_hash, str) or not self.book_hash.strip()
        ):
            raise DomainError("Polymarket book_hash must be a non-empty string when present")
        if self.negative_risk is not None and not isinstance(self.negative_risk, bool):
            raise DomainError("Polymarket negative_risk must be boolean when present")
        if self.minimum_order_size is not None:
            object.__setattr__(
                self,
                "minimum_order_size",
                parse_quantity(self.minimum_order_size, field="minimum_order_size"),
            )
        if self.tick_size is not None:
            object.__setattr__(self, "tick_size", parse_price(self.tick_size, field="tick_size"))
        if self.last_trade_price is not None:
            object.__setattr__(
                self,
                "last_trade_price",
                parse_price(self.last_trade_price, field="last_trade_price"),
            )

    @property
    def venue(self) -> Venue:
        return self.order_book.venue

    @property
    def market(self) -> MarketReference:
        return self.order_book.market

    @property
    def asset(self) -> ContractReference:
        contract = self.order_book.contract
        if contract is None:  # pragma: no cover - parser always supplies asset_id
            raise DomainError("Polymarket snapshot has no asset reference")
        return contract

    @property
    def timestamp(self) -> datetime:
        return self.order_book.timestamp

    @property
    def raw_ref(self) -> RawReference | None:
        return self.order_book.raw_ref

    @property
    def raw_refs(self) -> tuple[RawReference, ...]:
        return self.order_book.raw_refs


def parse_snapshot(envelope: RawEnvelope) -> PolymarketOrderBookSnapshot:
    """Parse only the documented, versioned Polymarket direct ``book`` shape."""

    if envelope.venue is not Venue.POLYMARKET:
        raise PayloadError("Polymarket parser received a non-Polymarket envelope")
    _schema(envelope)
    payload = envelope.original_payload
    if payload.get("event_type") != "book":
        raise PayloadError("Polymarket snapshot event_type must be 'book'")
    market = MarketReference(_required_non_empty_string(payload, "market"), Venue.POLYMARKET)
    asset = ContractReference(_required_non_empty_string(payload, "asset_id"), Venue.POLYMARKET)
    timestamp = parse_timestamp(_required(payload, "timestamp"), field="timestamp")
    bids = BookSide.normalized(BookSideKind.BID, _levels(_required(payload, "bids"), field="bids"))
    asks = BookSide.normalized(BookSideKind.ASK, _levels(_required(payload, "asks"), field="asks"))
    negative_risk: bool | None = None
    for field in ("negative_risk", "neg_risk"):
        if field in payload and payload[field] is not None:
            if not isinstance(payload[field], bool):
                raise PayloadError("Polymarket negative-risk flag must be boolean")
            if negative_risk is None:
                negative_risk = payload[field]
    try:
        last_trade_price = (
            parse_price(payload["last_trade_price"], field="last_trade_price")
            if payload.get("last_trade_price") is not None
            else None
        )
    except DomainError as exc:
        raise PayloadError("Polymarket last_trade_price is malformed") from exc
    book_hash = _optional_string(payload, "hash")
    normalized = OrderBookSnapshot(
        venue=Venue.POLYMARKET,
        market=market,
        contract=asset,
        timestamp=timestamp,
        bids=bids,
        asks=asks,
        raw_ref=envelope.raw_ref,
        raw_refs=(envelope.raw_ref,),
        warnings=envelope.warnings,
    )
    return PolymarketOrderBookSnapshot(
        order_book=normalized,
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
        book_hash=book_hash,
        minimum_order_size=_optional_quantity(payload, "minimum_order_size", "min_order_size"),
        tick_size=_optional_price(payload, "tick_size"),
        negative_risk=negative_risk,
        last_trade_price=last_trade_price,
    )


def apply_price_change(
    current: PolymarketOrderBookSnapshot,
    envelope: RawEnvelope,
) -> PolymarketOrderBookSnapshot:
    """Apply direct-schema price-level replacements to a local snapshot."""

    if envelope.venue is not Venue.POLYMARKET:
        raise PayloadError("Polymarket update received a non-Polymarket envelope")
    _schema(envelope)
    if current.schema_version != envelope.schema_version:
        raise PayloadError("Polymarket update schema does not match current snapshot")
    payload = envelope.original_payload
    if payload.get("event_type") != "price_change":
        raise PayloadError("Polymarket update event_type must be 'price_change'")
    market = _required_non_empty_string(payload, "market")
    if market != current.market.value:
        raise PayloadError("Polymarket update market does not match current snapshot")
    changes = _required(payload, "price_changes")
    if not isinstance(changes, (list, tuple)):
        raise PayloadError("Polymarket price_changes must be a list")

    validated_changes: list[tuple[str, str, Decimal, Decimal]] = []
    for index, change in enumerate(changes):
        if not isinstance(change, Mapping):
            raise PayloadError(f"Polymarket price_changes[{index}] must be an object")
        for field in ("asset_id", "price", "size", "side", "hash"):
            if field not in change:
                raise PayloadError(f"Polymarket price_changes[{index}] requires {field}")
        asset_id = change["asset_id"]
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise PayloadError(f"Polymarket price_changes[{index}] asset_id must be non-empty")
        side = change["side"]
        if not isinstance(side, str) or side not in {"BUY", "SELL"}:
            raise PayloadError(f"Polymarket price_changes[{index}] side must be BUY or SELL")
        change_hash = change["hash"]
        if not isinstance(change_hash, str) or not change_hash.strip():
            raise PayloadError(f"Polymarket price_changes[{index}] hash must be non-empty")
        try:
            price = parse_price(change["price"], field="price")
            size = parse_quantity(change["size"], field="size")
        except DomainError as exc:
            raise PayloadError(
                f"Polymarket price_changes[{index}] price or size is malformed"
            ) from exc
        validated_changes.append((asset_id, side, price, size))

    bids = current.order_book.bids
    asks = current.order_book.asks
    ignored_entries = 0
    for asset_id, side, price, size in validated_changes:
        if asset_id != current.asset.value:
            ignored_entries += 1
            continue
        if side == "BUY":
            bids = bids.replace_level(price, size)
        else:
            asks = asks.replace_level(price, size)
    timestamp = parse_timestamp(_required(payload, "timestamp"), field="timestamp")
    update_warnings = list(current.order_book.warnings + envelope.warnings)
    if ignored_entries:
        update_warnings.append(
            WarningRecord(
                WarningCode.IGNORED_EVENT_ENTRY,
                f"ignored {ignored_entries} price change entries for other tokens",
                "asset_id",
            )
        )
    lineage = current.order_book.raw_refs
    if not lineage and current.raw_ref is not None:
        lineage = (current.raw_ref,)
    updated = OrderBookSnapshot(
        venue=Venue.POLYMARKET,
        market=current.market,
        contract=current.asset,
        timestamp=timestamp,
        bids=bids,
        asks=asks,
        raw_ref=envelope.raw_ref,
        raw_refs=lineage + (envelope.raw_ref,),
        warnings=tuple(update_warnings),
        validity=current.order_book.validity,
    )
    return PolymarketOrderBookSnapshot(
        order_book=updated,
        schema_version=POLYMARKET_DIRECT_SCHEMA_VERSION,
        book_hash=None,
        minimum_order_size=current.minimum_order_size,
        tick_size=current.tick_size,
        negative_risk=current.negative_risk,
        last_trade_price=current.last_trade_price,
    )
