"""Normalized order-book levels and snapshots.

Duplicate prices are aggregated in input order. A resulting zero-size level is
removed; negative sizes are rejected before aggregation.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from invariant_engine.domain.decimal_policy import parse_price, parse_quantity
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningRecord


class BookSideKind(StrEnum):
    BID = "bid"
    ASK = "ask"
    YES_BID = "yes_bid"
    NO_BID = "no_bid"
    YES_ASK = "yes_ask"
    NO_ASK = "no_ask"


@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        price = parse_price(self.price, field="price")
        size = parse_quantity(self.size, field="size")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "size", size)


@dataclass(frozen=True, slots=True)
class BookSide:
    kind: BookSideKind
    levels: tuple[PriceLevel, ...]
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BookSideKind):
            raise DomainError("book side kind must be a BookSideKind")
        if any(level.size == 0 for level in self.levels):
            raise DomainError("normalized book sides cannot contain zero-size levels")
        prices = tuple(level.price for level in self.levels)
        if self.kind in {BookSideKind.BID, BookSideKind.YES_BID, BookSideKind.NO_BID}:
            if prices != tuple(sorted(prices, reverse=True)):
                raise DomainError("bid levels must be sorted descending by price")
        else:
            if prices != tuple(sorted(prices)):
                raise DomainError("ask levels must be sorted ascending by price")

    @classmethod
    def normalized(
        cls,
        kind: BookSideKind,
        levels: Iterable[PriceLevel],
        *,
        warnings: tuple[WarningRecord, ...] = (),
    ) -> "BookSide":
        aggregated: dict[Decimal, Decimal] = {}
        for level in levels:
            if level.size < 0:
                raise DomainError("negative size is invalid")
            aggregated[level.price] = aggregated.get(level.price, Decimal("0")) + level.size
        normalized = [PriceLevel(price, size) for price, size in aggregated.items() if size != 0]
        normalized.sort(
            key=lambda level: level.price,
            reverse=kind in {BookSideKind.BID, BookSideKind.YES_BID, BookSideKind.NO_BID},
        )
        return cls(kind=kind, levels=tuple(normalized), warnings=warnings)

    def replace_level(self, price: Decimal, size: Decimal) -> "BookSide":
        replacement = PriceLevel(price, size)
        remaining = [level for level in self.levels if level.price != replacement.price]
        if replacement.size != 0:
            remaining.append(replacement)
        return BookSide.normalized(self.kind, remaining, warnings=self.warnings)


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    venue: Venue
    market: MarketReference
    contract: ContractReference | None
    timestamp: datetime
    bids: BookSide
    asks: BookSide
    sequence: int | None = None
    raw_ref: RawReference | None = None
    raw_refs: tuple[RawReference, ...] = ()
    warnings: tuple[WarningRecord, ...] = ()
    validity: StateValidity = StateValidity.VALID

    def __post_init__(self) -> None:
        if self.market.venue is not self.venue:
            raise DomainError("market reference venue does not match snapshot venue")
        if self.contract is not None and self.contract.venue is not self.venue:
            raise DomainError("contract reference venue does not match snapshot venue")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DomainError("snapshot timestamp must be timezone-aware")
        if self.bids.kind is not BookSideKind.BID:
            raise DomainError("normalized snapshot bids must use the bid side")
        if self.asks.kind is not BookSideKind.ASK:
            raise DomainError("normalized snapshot asks must use the ask side")
        if self.raw_ref is not None and self.raw_ref.venue is not self.venue:
            raise DomainError("raw reference venue does not match snapshot venue")
        if self.raw_ref is not None and not self.raw_refs:
            raise DomainError("raw reference requires a non-empty lineage")
        if any(raw_ref.venue is not self.venue for raw_ref in self.raw_refs):
            raise DomainError("raw lineage reference venue does not match snapshot venue")
        if self.raw_ref is not None and self.raw_refs and self.raw_refs[-1] != self.raw_ref:
            raise DomainError("latest raw reference must be the final lineage reference")
