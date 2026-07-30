"""Immutable raw fixture envelopes."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import FixtureReference, RawReference, Venue
from invariant_engine.domain.warnings import WarningRecord


class SourceType(StrEnum):
    FIXTURE_REST = "fixture_rest"
    FIXTURE_WEBSOCKET = "fixture_websocket"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class RawEnvelope:
    raw_ref: RawReference
    venue: Venue
    source_type: SourceType
    endpoint_or_channel: str
    capture_timestamp: datetime
    retrieval_timestamp: datetime | None
    fixture: FixtureReference
    schema_version: str | None
    original_payload: Mapping[str, Any]
    payload_sha256: str
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.original_payload, Mapping):
            raise DomainError("original_payload must be a mapping")
        object.__setattr__(self, "original_payload", _freeze(self.original_payload))
        if self.raw_ref.venue is not self.venue or self.fixture.venue is not self.venue:
            raise DomainError("raw and fixture references must match envelope venue")
        for label, timestamp in (
            ("capture", self.capture_timestamp),
            ("retrieval", self.retrieval_timestamp),
        ):
            if timestamp is not None and (
                timestamp.tzinfo is None or timestamp.utcoffset() is None
            ):
                raise DomainError(f"{label} timestamp must be timezone-aware")
        if re.fullmatch(r"[0-9a-f]{64}", self.payload_sha256) is None:
            raise DomainError("payload_sha256 must be 64 lowercase hexadecimal characters")
        if self.raw_ref.value != f"sha256:{self.payload_sha256}":
            raise DomainError("raw_ref must match payload_sha256")

    @classmethod
    def from_fixture_bytes(
        cls,
        *,
        venue: Venue,
        fixture: FixtureReference,
        data: bytes,
        source_type: SourceType,
        endpoint_or_channel: str,
        capture_timestamp: datetime,
        retrieval_timestamp: datetime | None = None,
        schema_version: str | None = None,
        warnings: tuple[WarningRecord, ...] = (),
    ) -> "RawEnvelope":
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DomainError("fixture bytes must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise DomainError("fixture root payload must be an object")
        digest = hashlib.sha256(data).hexdigest()
        return cls(
            raw_ref=RawReference(f"sha256:{digest}", venue),
            venue=venue,
            source_type=source_type,
            endpoint_or_channel=endpoint_or_channel,
            capture_timestamp=capture_timestamp,
            retrieval_timestamp=retrieval_timestamp,
            fixture=fixture,
            schema_version=schema_version,
            original_payload=_freeze(payload),
            payload_sha256=digest,
            warnings=warnings,
        )

    @classmethod
    def from_payload(
        cls,
        *,
        venue: Venue,
        fixture: FixtureReference,
        payload: Mapping[str, Any],
        source_type: SourceType,
        endpoint_or_channel: str,
        capture_timestamp: datetime,
        retrieval_timestamp: datetime | None = None,
        schema_version: str | None = None,
        warnings: tuple[WarningRecord, ...] = (),
    ) -> "RawEnvelope":
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return cls.from_fixture_bytes(
            venue=venue,
            fixture=fixture,
            data=data,
            source_type=source_type,
            endpoint_or_channel=endpoint_or_channel,
            capture_timestamp=capture_timestamp,
            retrieval_timestamp=retrieval_timestamp,
            schema_version=schema_version,
            warnings=warnings,
        )
