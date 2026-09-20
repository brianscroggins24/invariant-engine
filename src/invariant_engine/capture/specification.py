"""Validation and deterministic identity for capture specifications."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, DecimalException

from invariant_engine.capture.models import (
    CAPTURE_SPECIFICATION_SCHEMA_VERSION,
    CAPTURE_SPECIFICATION_SCHEMA_VERSION_V2,
    CaptureEnvironment,
    CaptureLimits,
    CaptureProvenance,
    CaptureSpecification,
    CaptureTarget,
)
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import Venue
from invariant_engine.serialization import stable_json_bytes

POLYMARKET_ORIGIN = "https://clob.polymarket.com"
POLYMARKET_US_ORIGIN = "https://gateway.polymarket.us"
KALSHI_DEMO_ORIGIN = "https://external-api.demo.kalshi.co"
KALSHI_PRODUCTION_ORIGIN = "https://external-api.kalshi.com"

_TOKEN = re.compile(r"[0-9]{1,128}", re.ASCII)
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,127}", re.ASCII)
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,127}", re.ASCII)
_COMPONENT = re.compile(r"[A-Za-z0-9._:/-]{1,128}", re.ASCII)
_FIXED_LIMITS = CaptureLimits()


class CaptureSpecificationError(DomainError):
    """The complete capture specification is outside the supported contract."""


def expected_origin(venue: Venue, environment: CaptureEnvironment) -> str:
    if venue is Venue.POLYMARKET and environment is CaptureEnvironment.PRODUCTION:
        return POLYMARKET_ORIGIN
    if venue is Venue.POLYMARKET_US and environment is CaptureEnvironment.PRODUCTION:
        return POLYMARKET_US_ORIGIN
    if venue is Venue.KALSHI and environment is CaptureEnvironment.DEMO:
        return KALSHI_DEMO_ORIGIN
    if venue is Venue.KALSHI and environment is CaptureEnvironment.PRODUCTION:
        return KALSHI_PRODUCTION_ORIGIN
    raise CaptureSpecificationError("unsupported venue and environment binding")


def request_path(target: CaptureTarget) -> str:
    if target.venue is Venue.POLYMARKET:
        return "/book?token_id=" + target.identifier
    if target.venue is Venue.POLYMARKET_US:
        return "/v1/markets/" + target.identifier + "/book"
    if target.venue is Venue.KALSHI:
        return "/trade-api/v2/markets/" + target.identifier + "/orderbook"
    raise CaptureSpecificationError("unsupported capture target venue")


def signing_path(target: CaptureTarget) -> str:
    if target.venue is not Venue.KALSHI:
        raise CaptureSpecificationError("only Kalshi targets have signing paths")
    return "/trade-api/v2/markets/" + target.identifier + "/orderbook"


def _validate_provenance(value: object, field: str) -> tuple[CaptureProvenance, ...]:
    if type(value) is not tuple:
        raise CaptureSpecificationError(f"{field} must be an immutable tuple")
    if not 1 <= len(value) <= 64:
        raise CaptureSpecificationError(f"{field} requires 1 through 64 references")
    result: list[CaptureProvenance] = []
    serialized: set[str] = set()
    for item in value:
        if type(item) is not CaptureProvenance:
            raise CaptureSpecificationError(f"{field} requires exact provenance values")
        if type(item.kind) is not str or type(item.value) is not str:
            raise CaptureSpecificationError(f"{field} components must be exact strings")
        if _COMPONENT.fullmatch(item.kind) is None or _COMPONENT.fullmatch(item.value) is None:
            raise CaptureSpecificationError(f"{field} contains an invalid component")
        encoded = f"{item.kind}:{item.value}"
        if len(encoded.encode("ascii")) > 512 or encoded in serialized:
            raise CaptureSpecificationError(f"{field} contains an invalid or duplicate reference")
        serialized.add(encoded)
        result.append(item)
    return tuple(result)


def _validate_limits(value: object) -> CaptureLimits:
    if type(value) is not CaptureLimits:
        raise CaptureSpecificationError("capture limits must use the exact model type")
    for field in (
        "connect_timeout_seconds",
        "inactivity_timeout_seconds",
        "elapsed_budget_seconds",
    ):
        if type(getattr(value, field)) is not Decimal:
            raise CaptureSpecificationError("capture timeout limits must use exact Decimal types")
    for field in (
        "max_header_fields",
        "max_header_pair_bytes",
        "max_header_bytes",
        "max_body_bytes",
        "body_chunk_bytes",
    ):
        if type(getattr(value, field)) is not int:
            raise CaptureSpecificationError("capture integer limits must use exact integer types")
    try:
        matches_fixed_policy = value == _FIXED_LIMITS
    except DecimalException as error:
        raise CaptureSpecificationError(
            "capture limits must equal the fixed local policy"
        ) from error
    if not matches_fixed_policy:
        raise CaptureSpecificationError("capture limits must equal the fixed local policy")
    return value


def validate_specification(value: object) -> CaptureSpecification:
    """Validate every nested value and return an exact immutable reconstruction."""

    if type(value) is not CaptureSpecification:
        raise CaptureSpecificationError("capture specification must use the exact model type")
    if type(value.schema_version) is not str or value.schema_version not in {
        CAPTURE_SPECIFICATION_SCHEMA_VERSION,
        CAPTURE_SPECIFICATION_SCHEMA_VERSION_V2,
    }:
        raise CaptureSpecificationError("unsupported capture specification version")
    if (
        type(value.specification_id) is not str
        or _COMPONENT.fullmatch(value.specification_id) is None
    ):
        raise CaptureSpecificationError("invalid capture specification ID")
    provenance = _validate_provenance(value.provenance, "specification provenance")
    if type(value.targets) is not tuple or not 1 <= len(value.targets) <= 64:
        raise CaptureSpecificationError("capture specification requires 1 through 64 targets")
    targets: list[CaptureTarget] = []
    seen: set[tuple[Venue, CaptureEnvironment, str, str]] = set()
    for position, target in enumerate(value.targets):
        if type(target) is not CaptureTarget:
            raise CaptureSpecificationError("targets must use the exact target type")
        if type(target.position) is not int or target.position != position:
            raise CaptureSpecificationError("target position does not match caller order")
        if type(target.venue) is not Venue or type(target.environment) is not CaptureEnvironment:
            raise CaptureSpecificationError("target venue and environment require exact enum types")
        if value.schema_version == CAPTURE_SPECIFICATION_SCHEMA_VERSION:
            if target.venue not in {Venue.POLYMARKET, Venue.KALSHI}:
                raise CaptureSpecificationError(
                    "target venue is unsupported by specification version"
                )
        elif target.venue not in {Venue.POLYMARKET_US, Venue.KALSHI}:
            raise CaptureSpecificationError("target venue is unsupported by specification version")
        if type(target.origin) is not str or target.origin != expected_origin(
            target.venue, target.environment
        ):
            raise CaptureSpecificationError("target origin is not bound to venue and environment")
        if type(target.identifier) is not str:
            raise CaptureSpecificationError("target identifier must be an exact string")
        if target.venue is Venue.POLYMARKET:
            grammar = _TOKEN
        elif target.venue is Venue.POLYMARKET_US:
            grammar = _SLUG
        elif target.venue is Venue.KALSHI:
            grammar = _TICKER
        else:
            raise CaptureSpecificationError("unsupported capture target venue")
        if grammar.fullmatch(target.identifier) is None:
            raise CaptureSpecificationError("target identifier is outside the local grammar")
        limits = _validate_limits(target.limits)
        target_provenance = _validate_provenance(target.provenance, "target provenance")
        identity = (target.venue, target.environment, target.origin, target.identifier)
        if identity in seen:
            raise CaptureSpecificationError("duplicate capture target")
        seen.add(identity)
        targets.append(
            CaptureTarget(
                position=position,
                venue=target.venue,
                environment=target.environment,
                origin=target.origin,
                identifier=target.identifier,
                limits=limits,
                provenance=target_provenance,
            )
        )
    rebuilt = CaptureSpecification(
        schema_version=value.schema_version,
        specification_id=value.specification_id,
        targets=tuple(targets),
        provenance=provenance,
    )
    if stable_json_bytes(rebuilt) != stable_json_bytes(value):
        raise CaptureSpecificationError("specification material cannot be reconstructed exactly")
    return rebuilt


def specification_fingerprint(value: CaptureSpecification) -> str:
    validated = validate_specification(value)
    return hashlib.sha256(stable_json_bytes(validated)).hexdigest()


__all__ = [
    "CaptureSpecificationError",
    "KALSHI_DEMO_ORIGIN",
    "KALSHI_PRODUCTION_ORIGIN",
    "POLYMARKET_ORIGIN",
    "POLYMARKET_US_ORIGIN",
    "expected_origin",
    "request_path",
    "signing_path",
    "specification_fingerprint",
    "validate_specification",
]
