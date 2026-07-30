"""Kalshi-native fixture models and pure parsers.

The Kalshi order-book payload does not carry the price convention used by the
capture. Callers must provide that context explicitly; this module never
infers it from price values.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from invariant_engine.domain.decimal_policy import ONE, parse_decimal, parse_price
from invariant_engine.domain.errors import DomainError, PayloadError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.domain.order_book import BookSide, BookSideKind, PriceLevel
from invariant_engine.domain.time import parse_timestamp
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.provenance.raw_envelope import RawEnvelope

KALSHI_ORDERBOOK_SCHEMA_VERSION = "kalshi-orderbook-v1"


class KalshiPriceConvention(StrEnum):
    """Price scale used by the captured Kalshi order-book message."""

    OUTCOME_LEG = "outcome_leg"
    UNIFIED_YES_LEG = "unified_yes_leg"


class KalshiNativeSideKind(StrEnum):
    """Raw venue side, independent of the selected price convention."""

    YES = "yes"
    NO = "no"


class KalshiTimestampSource(StrEnum):
    VENUE = "venue"
    CAPTURE_FALLBACK = "capture_fallback"


def _normalize_timestamp_source(value: KalshiTimestampSource | str) -> KalshiTimestampSource:
    try:
        return KalshiTimestampSource(value)
    except (TypeError, ValueError) as exc:
        raise DomainError("Kalshi timestamp_source is unsupported") from exc


def _message(envelope: RawEnvelope) -> Mapping[str, Any]:
    payload = envelope.original_payload
    message = payload.get("msg")
    if not isinstance(message, Mapping):
        raise PayloadError("Kalshi payload requires an object msg")
    return message


def _required(message: Mapping[str, Any], field: str) -> Any:
    if field not in message:
        raise PayloadError(f"Kalshi payload is missing {field}")
    return message[field]


def _required_string(message: Mapping[str, Any], field: str) -> str:
    value = _required(message, field)
    if not isinstance(value, str) or not value.strip():
        raise PayloadError(f"Kalshi {field} must be a non-empty string")
    return value


def _required_positive_int(payload: Mapping[str, Any], field: str) -> int:
    value = _required(payload, field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PayloadError(f"Kalshi {field} must be a positive integer")
    return value


def _schema(envelope: RawEnvelope) -> None:
    if envelope.schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION:
        raise PayloadError(
            f"Kalshi parser requires schema_version {KALSHI_ORDERBOOK_SCHEMA_VERSION!r}"
        )


def _native_levels(value: Any, *, field: str) -> list[PriceLevel]:
    if not isinstance(value, (list, tuple)):
        raise PayloadError(f"Kalshi {field} must be a list")
    result: list[PriceLevel] = []
    for index, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise PayloadError(f"Kalshi {field}[{index}] must be [price, size]")
        try:
            result.append(PriceLevel(item[0], item[1]))
        except DomainError as exc:
            raise PayloadError(f"Kalshi {field}[{index}] is malformed") from exc
    return result


def _timestamp(
    message: Mapping[str, Any], envelope: RawEnvelope
) -> tuple[datetime, KalshiTimestampSource, tuple[WarningRecord, ...]]:
    if "ts" in message:
        return parse_timestamp(message["ts"], field="ts"), KalshiTimestampSource.VENUE, ()
    if "ts_ms" in message:
        return parse_timestamp(message["ts_ms"], field="ts_ms"), KalshiTimestampSource.VENUE, ()
    return (
        envelope.capture_timestamp,
        KalshiTimestampSource.CAPTURE_FALLBACK,
        (
            WarningRecord(
                WarningCode.UNAVAILABLE_FIELD, "Kalshi payload has no venue timestamp", "timestamp"
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class KalshiMarketIdentity:
    """Kalshi's venue-native market ticker and market ID."""

    market_ticker: str
    market_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.market_ticker, str) or not self.market_ticker.strip():
            raise DomainError("Kalshi market_ticker must be a non-empty string")
        if not isinstance(self.market_id, str) or not self.market_id.strip():
            raise DomainError("Kalshi market_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class KalshiNativeBookSide:
    """Immutable raw Kalshi side whose price scale is capture-context dependent."""

    kind: KalshiNativeSideKind
    levels: tuple[PriceLevel, ...]
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, KalshiNativeSideKind):
            raise DomainError("Kalshi native side kind must be a KalshiNativeSideKind")
        if any(not isinstance(level, PriceLevel) for level in self.levels):
            raise DomainError("Kalshi native side levels must be PriceLevel values")
        if any(level.size <= 0 for level in self.levels):
            raise DomainError("normalized Kalshi native sides cannot contain zero-size levels")
        prices = tuple(level.price for level in self.levels)
        if prices != tuple(sorted(prices, reverse=True)):
            raise DomainError("Kalshi native levels must be sorted descending by price")

    @classmethod
    def normalized(
        cls,
        kind: KalshiNativeSideKind,
        levels: Iterable[PriceLevel],
        *,
        warnings: tuple[WarningRecord, ...] = (),
    ) -> "KalshiNativeBookSide":
        if not isinstance(kind, KalshiNativeSideKind):
            raise DomainError("Kalshi native side kind must be a KalshiNativeSideKind")
        aggregated: dict[Decimal, Decimal] = {}
        for level in levels:
            if not isinstance(level, PriceLevel):
                raise DomainError("Kalshi native side levels must be PriceLevel values")
            aggregated[level.price] = aggregated.get(level.price, Decimal("0")) + level.size
        normalized = [
            PriceLevel(price, size) for price, size in aggregated.items() if size != Decimal("0")
        ]
        normalized.sort(key=lambda level: level.price, reverse=True)
        return cls(kind=kind, levels=tuple(normalized), warnings=warnings)

    def replace_level(self, price: Decimal, size: Decimal) -> "KalshiNativeBookSide":
        replacement = PriceLevel(price, size)
        remaining = [level for level in self.levels if level.price != replacement.price]
        if replacement.size != Decimal("0"):
            remaining.append(replacement)
        return self.normalized(self.kind, remaining, warnings=self.warnings)


@dataclass(frozen=True, slots=True)
class KalshiOrderBookSnapshot:
    venue: Venue
    market: KalshiMarketIdentity
    schema_version: str
    timestamp: datetime
    timestamp_source: KalshiTimestampSource | str
    yes_side: KalshiNativeBookSide
    no_side: KalshiNativeBookSide
    session_id: int
    sequence: int
    price_convention: KalshiPriceConvention
    raw_ref: RawReference
    raw_refs: tuple[RawReference, ...]
    warnings: tuple[WarningRecord, ...]
    validity: StateValidity = StateValidity.VALID

    def __post_init__(self) -> None:
        if self.venue is not Venue.KALSHI:
            raise DomainError("Kalshi snapshot venue must be kalshi")
        if not isinstance(self.market, KalshiMarketIdentity):
            raise DomainError("Kalshi snapshot market must be KalshiMarketIdentity")
        if not isinstance(self.yes_side, KalshiNativeBookSide) or not isinstance(
            self.no_side, KalshiNativeBookSide
        ):
            raise DomainError("Kalshi snapshot native sides must be KalshiNativeBookSide values")
        if self.schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION:
            raise DomainError("unsupported Kalshi schema version")
        if not isinstance(self.timestamp, datetime):
            raise DomainError("Kalshi snapshot timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DomainError("Kalshi snapshot timestamp must be timezone-aware")
        object.__setattr__(
            self, "timestamp_source", _normalize_timestamp_source(self.timestamp_source)
        )
        if self.yes_side.kind is not KalshiNativeSideKind.YES:
            raise DomainError("Kalshi yes_side must use the YES native side kind")
        if self.no_side.kind is not KalshiNativeSideKind.NO:
            raise DomainError("Kalshi no_side must use the NO native side kind")
        if isinstance(self.session_id, bool) or not isinstance(self.session_id, int):
            raise DomainError("Kalshi session_id must be an integer")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise DomainError("Kalshi sequence must be an integer")
        if self.session_id <= 0 or self.sequence <= 0:
            raise DomainError("Kalshi session_id and sequence must be positive")
        if not isinstance(self.price_convention, KalshiPriceConvention):
            raise DomainError("Kalshi price_convention must be a KalshiPriceConvention")
        if not isinstance(self.validity, StateValidity):
            raise DomainError("snapshot validity must be a StateValidity")
        if not isinstance(self.raw_ref, RawReference) or self.raw_ref.venue is not self.venue:
            raise DomainError("Kalshi raw reference has the wrong venue")
        if not self.raw_refs or self.raw_refs[-1] != self.raw_ref:
            raise DomainError("Kalshi latest raw reference must be final in lineage")
        if any(
            not isinstance(raw_ref, RawReference) or raw_ref.venue is not self.venue
            for raw_ref in self.raw_refs
        ):
            raise DomainError("Kalshi lineage reference has the wrong venue")

    def interpreted_yes_bids(self) -> BookSide:
        """Return YES bids on the YES price scale."""

        return BookSide.normalized(
            BookSideKind.YES_BID, self.yes_side.levels, warnings=self.yes_side.warnings
        )

    def interpreted_no_bids(self) -> BookSide:
        """Return NO bids on the NO price scale."""

        if self.price_convention is KalshiPriceConvention.OUTCOME_LEG:
            return BookSide.normalized(
                BookSideKind.NO_BID, self.no_side.levels, warnings=self.no_side.warnings
            )
        if self.price_convention is KalshiPriceConvention.UNIFIED_YES_LEG:
            levels = [PriceLevel(ONE - level.price, level.size) for level in self.no_side.levels]
            return BookSide.normalized(
                BookSideKind.NO_BID,
                levels,
                warnings=self.no_side.warnings
                + (
                    WarningRecord(
                        WarningCode.DERIVED_VALUE,
                        "NO bids converted from unified YES-leg prices",
                    ),
                ),
            )
        raise DomainError("unsupported Kalshi price convention")

    def derived_yes_asks(self) -> BookSide:
        if self.price_convention is KalshiPriceConvention.OUTCOME_LEG:
            levels = [PriceLevel(ONE - level.price, level.size) for level in self.no_side.levels]
            message = "YES asks derived as complements of native NO-leg prices"
        elif self.price_convention is KalshiPriceConvention.UNIFIED_YES_LEG:
            levels = [PriceLevel(level.price, level.size) for level in self.no_side.levels]
            message = "YES asks read from NO-side levels already reported on the YES scale"
        else:
            raise DomainError("unsupported Kalshi price convention")
        return BookSide.normalized(
            BookSideKind.YES_ASK,
            levels,
            warnings=self.warnings + (WarningRecord(WarningCode.DERIVED_VALUE, message),),
        )

    def derived_no_asks(self) -> BookSide:
        levels = [PriceLevel(ONE - level.price, level.size) for level in self.yes_side.levels]
        return BookSide.normalized(
            BookSideKind.NO_ASK,
            levels,
            warnings=self.warnings
            + (WarningRecord(WarningCode.DERIVED_VALUE, "NO asks derived from YES-side prices"),),
        )


def parse_snapshot(
    envelope: RawEnvelope, *, price_convention: KalshiPriceConvention
) -> KalshiOrderBookSnapshot:
    if envelope.venue is not Venue.KALSHI:
        raise PayloadError("Kalshi parser received a non-Kalshi envelope")
    _schema(envelope)
    if envelope.original_payload.get("type") != "orderbook_snapshot":
        raise PayloadError("Kalshi snapshot type must be 'orderbook_snapshot'")
    if not isinstance(price_convention, KalshiPriceConvention):
        raise PayloadError("Kalshi price_convention must be a KalshiPriceConvention")
    message = _message(envelope)
    market = KalshiMarketIdentity(
        _required_string(message, "market_ticker"),
        _required_string(message, "market_id"),
    )
    timestamp, timestamp_source, timestamp_warnings = _timestamp(message, envelope)
    sequence = _required_positive_int(envelope.original_payload, "seq")
    sid = _required_positive_int(envelope.original_payload, "sid")
    yes_value = message.get("yes_dollars_fp", [])
    no_value = message.get("no_dollars_fp", [])
    return KalshiOrderBookSnapshot(
        venue=Venue.KALSHI,
        market=market,
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
        timestamp=timestamp,
        timestamp_source=timestamp_source,
        yes_side=KalshiNativeBookSide.normalized(
            KalshiNativeSideKind.YES,
            _native_levels(yes_value, field="yes_dollars_fp"),
        ),
        no_side=KalshiNativeBookSide.normalized(
            KalshiNativeSideKind.NO,
            _native_levels(no_value, field="no_dollars_fp"),
        ),
        session_id=sid,
        sequence=sequence,
        price_convention=price_convention,
        raw_ref=envelope.raw_ref,
        raw_refs=(envelope.raw_ref,),
        warnings=envelope.warnings + timestamp_warnings,
    )


@dataclass(frozen=True, slots=True)
class KalshiOrderBookDelta:
    market: KalshiMarketIdentity
    schema_version: str
    timestamp: datetime
    timestamp_source: KalshiTimestampSource | str
    sequence: int
    session_id: int
    price_convention: KalshiPriceConvention
    side: KalshiNativeSideKind
    price: Decimal
    delta_size: Decimal
    raw_ref: RawReference
    warnings: tuple[WarningRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION:
            raise DomainError("unsupported Kalshi schema version")
        if not isinstance(self.market, KalshiMarketIdentity):
            raise DomainError("Kalshi delta market must be KalshiMarketIdentity")
        if not isinstance(self.side, KalshiNativeSideKind):
            raise DomainError("Kalshi delta side must be a KalshiNativeSideKind")
        if isinstance(self.session_id, bool) or not isinstance(self.session_id, int):
            raise DomainError("Kalshi session_id must be an integer")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise DomainError("Kalshi sequence must be an integer")
        if self.session_id <= 0 or self.sequence <= 0:
            raise DomainError("Kalshi session_id and sequence must be positive")
        if not isinstance(self.price_convention, KalshiPriceConvention):
            raise DomainError("Kalshi price_convention must be a KalshiPriceConvention")
        if not isinstance(self.timestamp, datetime):
            raise DomainError("Kalshi delta timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DomainError("Kalshi delta timestamp must be timezone-aware")
        object.__setattr__(
            self, "timestamp_source", _normalize_timestamp_source(self.timestamp_source)
        )
        if not isinstance(self.raw_ref, RawReference) or self.raw_ref.venue is not Venue.KALSHI:
            raise DomainError("Kalshi delta raw reference must belong to Kalshi")
        object.__setattr__(self, "price", parse_price(self.price, field="price"))
        object.__setattr__(self, "delta_size", parse_decimal(self.delta_size, field="delta_size"))


def parse_delta(
    envelope: RawEnvelope, *, price_convention: KalshiPriceConvention
) -> KalshiOrderBookDelta:
    if envelope.venue is not Venue.KALSHI:
        raise PayloadError("Kalshi parser received a non-Kalshi envelope")
    _schema(envelope)
    if envelope.original_payload.get("type") != "orderbook_delta":
        raise PayloadError("Kalshi delta type must be 'orderbook_delta'")
    if not isinstance(price_convention, KalshiPriceConvention):
        raise PayloadError("Kalshi price_convention must be a KalshiPriceConvention")
    message = _message(envelope)
    market = KalshiMarketIdentity(
        _required_string(message, "market_ticker"),
        _required_string(message, "market_id"),
    )
    side_value = _required_string(message, "side")
    if side_value == "yes":
        side = KalshiNativeSideKind.YES
    elif side_value == "no":
        side = KalshiNativeSideKind.NO
    else:
        raise PayloadError("Kalshi delta side must be yes or no")
    timestamp, timestamp_source, timestamp_warnings = _timestamp(message, envelope)
    return KalshiOrderBookDelta(
        market=market,
        schema_version=KALSHI_ORDERBOOK_SCHEMA_VERSION,
        timestamp=timestamp,
        timestamp_source=timestamp_source,
        sequence=_required_positive_int(envelope.original_payload, "seq"),
        session_id=_required_positive_int(envelope.original_payload, "sid"),
        price_convention=price_convention,
        side=side,
        price=parse_price(_required(message, "price_dollars"), field="price_dollars"),
        delta_size=parse_decimal(_required(message, "delta_fp"), field="delta_fp"),
        raw_ref=envelope.raw_ref,
        warnings=envelope.warnings + timestamp_warnings,
    )


def apply_delta(
    current: KalshiOrderBookSnapshot, delta: KalshiOrderBookDelta
) -> KalshiOrderBookSnapshot:
    if delta.market != current.market:
        raise PayloadError("Kalshi delta market does not match current snapshot")
    if delta.session_id != current.session_id:
        raise PayloadError("Kalshi delta sid does not match current snapshot")
    if delta.schema_version != current.schema_version:
        raise PayloadError("Kalshi delta schema does not match current snapshot")
    if delta.price_convention is not current.price_convention:
        raise PayloadError("Kalshi delta price convention does not match current snapshot")
    if delta.sequence != current.sequence + 1:
        raise PayloadError("Kalshi delta sequence is not contiguous with current snapshot")
    if delta.side is KalshiNativeSideKind.YES:
        current_side = current.yes_side
    elif delta.side is KalshiNativeSideKind.NO:
        current_side = current.no_side
    else:
        raise PayloadError("Kalshi delta has an unsupported native side")
    existing = next(
        (level.size for level in current_side.levels if level.price == delta.price), Decimal("0")
    )
    new_size = existing + delta.delta_size
    if new_size < 0:
        raise PayloadError("Kalshi delta would make a level negative")
    updated_side = current_side.replace_level(delta.price, new_size)
    if delta.side is KalshiNativeSideKind.YES:
        yes_side = updated_side
        no_side = current.no_side
    elif delta.side is KalshiNativeSideKind.NO:
        yes_side = current.yes_side
        no_side = updated_side
    else:
        raise PayloadError("Kalshi delta has an unsupported native side")
    return KalshiOrderBookSnapshot(
        venue=current.venue,
        market=current.market,
        schema_version=current.schema_version,
        timestamp=delta.timestamp,
        timestamp_source=delta.timestamp_source,
        yes_side=yes_side,
        no_side=no_side,
        session_id=current.session_id,
        sequence=delta.sequence,
        price_convention=current.price_convention,
        raw_ref=delta.raw_ref,
        raw_refs=current.raw_refs + (delta.raw_ref,),
        warnings=current.warnings + delta.warnings,
        validity=current.validity,
    )
