"""Direct bounded HTTPS transport for the three allowlisted capture operations."""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import re
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, BinaryIO, Protocol, cast
from urllib.parse import urlsplit

from invariant_engine.capture.models import (
    CAPTURE_SPECIFICATION_SCHEMA_VERSION,
    AcquisitionOutcome,
    CaptureSpecification,
    CaptureTarget,
    RetentionState,
)
from invariant_engine.capture.specification import (
    expected_origin,
    request_path,
    validate_specification,
)
from invariant_engine.domain.ids import Venue


class TransportFailureKind(StrEnum):
    HEADERS = "headers"
    OVERSIZED = "oversized"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    CONFIDENTIALITY = "confidentiality"


@dataclass(frozen=True, slots=True)
class TransportResult:
    failure: TransportFailureKind | None
    http_status: int | None
    content_length: int | None
    content_type: str | None
    acquisition_outcome: AcquisitionOutcome
    retention_state: RetentionState
    received_byte_count: int
    retained_body: bytes | None
    retained_body_sha256: str | None
    suppression_source: str | None


class Clock(Protocol):
    def monotonic(self) -> float: ...


class _SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class _BudgetExceeded(TimeoutError):
    pass


class _ChunkedReadFailure(Exception):
    def __init__(self, failure: TransportFailureKind, partial: bytes) -> None:
        super().__init__("chunked body acquisition failed")
        self.failure = failure
        self.partial = partial


_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", re.ASCII)
_MEDIA_TYPE = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+/[!#$%&'*+.^_`|~0-9A-Za-z-]+", re.ASCII)
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,256}", re.ASCII)
_TIMESTAMP = re.compile(r"[0-9]{1,20}", re.ASCII)
_MAX_HEADER_FIELDS = 100
_MAX_HEADER_PAIR_BYTES = 8_192
_MAX_HEADER_BYTES = 32_768
_MAX_RAW_HEADER_BYTES = _MAX_HEADER_BYTES + (3 * _MAX_HEADER_FIELDS)
_MAX_TRAILER_LINES = 100
_MAX_TRAILER_LINE_BYTES = 8_192
_MAX_TRAILER_BYTES = 32_768


@dataclass(slots=True)
class _HeaderAccounting:
    field_count: int = 0
    pair_bytes: int = 0
    invalid: bool = False
    reflected: bool = False


def _read_initial_headers(
    fp: BinaryIO,
    accounting: _HeaderAccounting,
    quarantine: bytearray,
    secrets: tuple[bytes, ...],
    before_read: Callable[[], None],
    after_read: Callable[[], None],
) -> tuple[tuple[bytes, ...], bool]:
    lines: list[bytes] = []
    while True:
        before_read()
        line = fp.readline(_MAX_HEADER_PAIR_BYTES + 4)
        lines.append(line)
        remaining_quarantine = _MAX_RAW_HEADER_BYTES - len(quarantine)
        if remaining_quarantine > 0:
            quarantine.extend(line[:remaining_quarantine])
        if secrets and any(secret in line for secret in secrets):
            accounting.reflected = True
        if len(line) > _MAX_HEADER_PAIR_BYTES + 3:
            accounting.invalid = True
            after_read()
            return tuple(lines), True
        if line in (b"\r\n", b"\n"):
            after_read()
            return tuple(lines), accounting.invalid
        if line == b"":
            accounting.invalid = True
            after_read()
            return tuple(lines), True
        accounting.field_count += 1
        if accounting.field_count > _MAX_HEADER_FIELDS:
            accounting.invalid = True
            after_read()
            return tuple(lines), True
        if line.endswith(b"\r\n"):
            field = line[:-2]
        elif line.endswith(b"\n"):
            field = line[:-1]
        else:
            accounting.invalid = True
            field = line
        if field.startswith((b" ", b"\t")) or b":" not in field:
            accounting.invalid = True
            after_read()
            continue
        name, value = field.split(b":", 1)
        try:
            name_text = name.decode("ascii")
        except UnicodeDecodeError:
            accounting.invalid = True
        else:
            if _HEADER_NAME.fullmatch(name_text) is None:
                accounting.invalid = True
        normalized_value = value.strip(b" \t")
        pair_length = len(name) + len(normalized_value)
        accounting.pair_bytes += pair_length
        if pair_length > _MAX_HEADER_PAIR_BYTES or accounting.pair_bytes > _MAX_HEADER_BYTES:
            accounting.invalid = True
            after_read()
            return tuple(lines), True
        after_read()


def _validated_header_message(lines: tuple[bytes, ...]) -> http.client.HTTPMessage:
    message = http.client.HTTPMessage()
    for line in lines:
        if line in (b"\r\n", b"\n"):
            break
        field = line[:-2] if line.endswith(b"\r\n") else line[:-1]
        name, value = field.split(b":", 1)
        message[name.decode("ascii")] = value.strip(b" \t").decode("iso-8859-1")
    return message


class _StrictHTTPResponse(http.client.HTTPResponse):
    """HTTP response with bounded raw initial-header quarantine."""

    def __init__(
        self,
        sock: Any,
        debuglevel: int = 0,
        method: str | None = None,
        url: str | None = None,
        *,
        clock: Clock | None = None,
        started: float = 0.0,
        budget: float = 0.0,
        operation_timeout: float = 0.0,
        secrets: tuple[bytes, ...] = (),
    ) -> None:
        super().__init__(sock, debuglevel, method, url)
        self._capture_socket = sock
        self._capture_clock = clock
        self._capture_started = started
        self._capture_budget = budget
        self._capture_operation_timeout = operation_timeout
        self._capture_secrets = secrets
        self.capture_initial_header_bytes = b""
        self.capture_initial_header_invalid = False
        self.capture_initial_header_reflection = False
        self.capture_initial_header_failure: TransportFailureKind | None = None
        self.capture_trailer_failure: TransportFailureKind | None = None

    def _before_header_read(self) -> None:
        if self._capture_clock is not None:
            remaining = _remaining(self._capture_clock, self._capture_started, self._capture_budget)
            self._capture_socket.settimeout(min(self._capture_operation_timeout, remaining))

    def _after_header_read(self) -> None:
        if self._capture_clock is not None:
            _remaining(self._capture_clock, self._capture_started, self._capture_budget)

    def _failure_after_read(self, failure: TransportFailureKind) -> TransportFailureKind:
        try:
            self._after_header_read()
        except _BudgetExceeded:
            return TransportFailureKind.TIMEOUT
        return failure

    def _read_next_chunk_size_with_budget(self) -> int:
        self._before_header_read()
        try:
            return cast(int, self._read_next_chunk_size())  # type: ignore[attr-defined]
        finally:
            self._after_header_read()

    def _discard_chunk_end_with_budget(self) -> None:
        self._before_header_read()
        try:
            self._safe_read(2)  # type: ignore[attr-defined]
        finally:
            self._after_header_read()

    def _get_chunk_left_with_budget(self) -> int | None:
        chunk_left = self.chunk_left
        if not chunk_left:
            if chunk_left is not None:
                self._discard_chunk_end_with_budget()
            try:
                chunk_left = self._read_next_chunk_size_with_budget()
            except ValueError:
                self._close_conn()  # type: ignore[attr-defined]
                raise http.client.IncompleteRead(b"") from None
            if chunk_left < 0:
                self._close_conn()  # type: ignore[attr-defined]
                raise http.client.IncompleteRead(b"")
            if chunk_left == 0:
                self._read_and_discard_trailer()
                self._close_conn()  # type: ignore[attr-defined]
                chunk_left = None
            self.chunk_left = chunk_left
        return chunk_left

    def _read_chunked(self, amt: int | None = None) -> bytes:
        parts: list[bytes] = []
        while True:
            try:
                chunk_left = self._get_chunk_left_with_budget()
            except (TimeoutError, _BudgetExceeded):
                raise _ChunkedReadFailure(TransportFailureKind.TIMEOUT, b"".join(parts)) from None
            except (OSError, http.client.HTTPException, ssl.SSLError):
                raise _ChunkedReadFailure(TransportFailureKind.TRANSPORT, b"".join(parts)) from None
            if chunk_left is None:
                return b"".join(parts)
            read_amount = chunk_left
            final_read = False
            if amt is not None and amt <= chunk_left:
                read_amount = amt
                final_read = True
            try:
                self._before_header_read()
                part = self._safe_read(read_amount)  # type: ignore[attr-defined]
            except http.client.IncompleteRead as error:
                parts.append(error.partial)
                failure = self._failure_after_read(TransportFailureKind.TRANSPORT)
                raise _ChunkedReadFailure(
                    failure,
                    b"".join(parts),
                ) from None
            except (TimeoutError, _BudgetExceeded):
                failure = self._failure_after_read(TransportFailureKind.TIMEOUT)
                raise _ChunkedReadFailure(failure, b"".join(parts)) from None
            except (OSError, http.client.HTTPException, ssl.SSLError):
                failure = self._failure_after_read(TransportFailureKind.TRANSPORT)
                raise _ChunkedReadFailure(failure, b"".join(parts)) from None
            parts.append(part)
            try:
                self._after_header_read()
            except _BudgetExceeded:
                raise _ChunkedReadFailure(TransportFailureKind.TIMEOUT, b"".join(parts)) from None
            self.chunk_left = chunk_left - read_amount
            if final_read:
                return b"".join(parts)
            if amt is not None:
                amt -= read_amount

    def _read_and_discard_trailer(self) -> None:
        line_count = 0
        total_bytes = 0
        while True:
            read_limit = min(
                _MAX_TRAILER_LINE_BYTES + 1,
                _MAX_TRAILER_BYTES - total_bytes + 1,
            )
            try:
                self._before_header_read()
                line = self.fp.readline(read_limit)
                self._after_header_read()
            except (TimeoutError, _BudgetExceeded):
                self.capture_trailer_failure = TransportFailureKind.TIMEOUT
                return
            except (OSError, http.client.HTTPException, ssl.SSLError):
                self.capture_trailer_failure = TransportFailureKind.TRANSPORT
                return
            total_bytes += len(line)
            if (
                len(line) > _MAX_TRAILER_LINE_BYTES
                or total_bytes > _MAX_TRAILER_BYTES
                or line == b""
                or not line.endswith(b"\n")
            ):
                self.capture_trailer_failure = TransportFailureKind.TRANSPORT
                return
            if line in (b"\r\n", b"\n"):
                return
            line_count += 1
            if line_count > _MAX_TRAILER_LINES:
                self.capture_trailer_failure = TransportFailureKind.TRANSPORT
                return

    def _finish_header_failure(self, failure: TransportFailureKind) -> None:
        self.capture_initial_header_failure = failure
        self.headers = self.msg = http.client.HTTPMessage()
        self.chunked = False
        self.will_close = True
        self.length = 0

    def _set_response_line(self, version: str, status: int, reason: str) -> None:
        self.code = self.status = status
        self.reason = reason.strip()
        if version in ("HTTP/1.0", "HTTP/0.9"):
            self.version = 10
        elif version.startswith("HTTP/1."):
            self.version = 11
        else:
            raise http.client.UnknownProtocol(version)

    def begin(self) -> None:
        if self.headers is not None:
            return
        accounting = _HeaderAccounting()
        quarantine = bytearray()
        lines: tuple[bytes, ...] = ()
        try:
            while True:
                self._before_header_read()
                version, status, reason = self._read_status()
                self._set_response_line(version, status, reason)
                self._after_header_read()
                lines, invalid = _read_initial_headers(
                    self.fp,
                    accounting,
                    quarantine,
                    self._capture_secrets,
                    self._before_header_read,
                    self._after_header_read,
                )
                if invalid or status != http.client.CONTINUE:
                    break
        except (TimeoutError, _BudgetExceeded):
            self._finish_header_failure(TransportFailureKind.TIMEOUT)
        except (OSError, http.client.HTTPException, ssl.SSLError):
            self._finish_header_failure(TransportFailureKind.TRANSPORT)
        self.capture_initial_header_bytes = bytes(quarantine)
        self.capture_initial_header_invalid = accounting.invalid
        self.capture_initial_header_reflection = accounting.reflected
        if self.capture_initial_header_failure is not None:
            return
        if accounting.invalid:
            self._finish_header_failure(TransportFailureKind.HEADERS)
            return
        self.headers = self.msg = _validated_header_message(lines)
        transfer_encoding = self.headers.get("transfer-encoding")
        self.chunked = bool(transfer_encoding and transfer_encoding.lower() == "chunked")
        self.chunk_left = None
        self.will_close = self._check_close()
        self.length = None
        length = self.headers.get("content-length")
        if length and not self.chunked:
            try:
                parsed_length = int(length)
            except ValueError:
                pass
            else:
                if parsed_length >= 0:
                    self.length = parsed_length
        if (
            status == http.client.NO_CONTENT
            or status == http.client.NOT_MODIFIED
            or 100 <= status < 200
            or self._method == "HEAD"
        ):
            self.length = 0
        if not self.will_close and not self.chunked and self.length is None:
            self.will_close = True


class _DirectHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that uses one resolved address and no ambient handlers."""

    response_class = _StrictHTTPResponse

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._capture_context = context
        self._capture_clock: Clock | None = None
        self._capture_started = 0.0
        self._capture_budget = timeout
        self._capture_operation_timeout = timeout
        self._capture_header_secrets: tuple[bytes, ...] = ()
        self.response_class = self._create_response  # type: ignore[assignment]

    def configure_budget(
        self,
        clock: Clock,
        started: float,
        budget: float,
        operation_timeout: float,
    ) -> None:
        self._capture_clock = clock
        self._capture_started = started
        self._capture_budget = budget
        self._capture_operation_timeout = operation_timeout

    def configure_header_acquisition(
        self,
        secrets: tuple[bytes, ...],
        operation_timeout: float,
    ) -> None:
        self._capture_header_secrets = secrets
        self._capture_operation_timeout = operation_timeout

    def _create_response(
        self,
        sock: Any,
        debuglevel: int = 0,
        method: str | None = None,
        url: str | None = None,
    ) -> _StrictHTTPResponse:
        return _StrictHTTPResponse(
            sock,
            debuglevel,
            method,
            url,
            clock=self._capture_clock,
            started=self._capture_started,
            budget=self._capture_budget,
            operation_timeout=self._capture_operation_timeout,
            secrets=self._capture_header_secrets,
        )

    def _stage_timeout(self) -> float:
        if self._capture_clock is None:
            return self._capture_operation_timeout
        return min(
            self._capture_operation_timeout,
            _remaining(self._capture_clock, self._capture_started, self._capture_budget),
        )

    def _stage_complete(self) -> None:
        if self._capture_clock is not None:
            _remaining(self._capture_clock, self._capture_started, self._capture_budget)

    def connect(self) -> None:
        self._stage_timeout()
        infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        self._stage_complete()
        if not infos:
            raise OSError("name resolution returned no address")
        family, socktype, protocol, _, address = infos[0]
        raw = socket.socket(family, socktype, protocol)
        try:
            raw.settimeout(self._stage_timeout())
            raw.connect(address)
            self._stage_complete()
            raw.settimeout(self._stage_timeout())
            self.sock = self._capture_context.wrap_socket(raw, server_hostname=self.host)
            self._stage_complete()
        except BaseException:
            raw.close()
            raise


def _remaining(clock: Clock, started: float, budget: float) -> float:
    remaining = budget - (clock.monotonic() - started)
    if remaining <= 0:
        raise _BudgetExceeded
    return remaining


def _set_timeout(
    connection: http.client.HTTPSConnection,
    clock: Clock,
    started: float,
    inactivity: float,
    budget: float,
) -> None:
    remaining = _remaining(clock, started, budget)
    timeout = min(inactivity, remaining)
    connection.timeout = timeout
    if connection.sock is not None:
        connection.sock.settimeout(timeout)


def _contains_secret(data: bytes, secrets: tuple[bytes, ...]) -> bool:
    if any(secret in data for secret in secrets):
        return True
    index = 0
    while index < len(data):
        start = data.find(b'"', index)
        if start < 0:
            break
        cursor = start + 1
        escaped = False
        while cursor < len(data):
            byte = data[cursor]
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                token = data[start : cursor + 1]
                try:
                    decoded = json.loads(token.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    break
                if isinstance(decoded, str):
                    try:
                        encoded = decoded.encode("utf-8")
                    except UnicodeEncodeError:
                        pass
                    else:
                        if any(secret in encoded for secret in secrets):
                            return True
                index = cursor + 1
                break
            cursor += 1
        else:
            break
        if index <= start:
            index = cursor + 1
    return False


def _header_metadata(
    headers: list[tuple[str, str]],
    secrets: tuple[bytes, ...],
    target: CaptureTarget,
) -> tuple[int | None, str | None, bool]:
    try:
        header_blob = b"\x00".join(
            name.encode("iso-8859-1") + b":" + value.encode("iso-8859-1") for name, value in headers
        )
    except UnicodeEncodeError:
        reflected = any(
            secret.decode("ascii") in name or secret.decode("ascii") in value
            for name, value in headers
            for secret in secrets
        )
        if reflected:
            return None, None, True
        raise ValueError from None
    if secrets and _contains_secret(header_blob, secrets):
        return None, None, True
    if len(headers) > target.limits.max_header_fields:
        raise ValueError
    total = 0
    lengths: list[str] = []
    encodings: list[str] = []
    transfer_encodings: list[str] = []
    content_types: list[str] = []
    for name, value in headers:
        try:
            name_bytes = name.encode("iso-8859-1")
            value_bytes = value.encode("iso-8859-1")
        except UnicodeEncodeError as exc:
            raise ValueError from exc
        pair_length = len(name_bytes) + len(value_bytes)
        total += pair_length
        if (
            pair_length > target.limits.max_header_pair_bytes
            or total > target.limits.max_header_bytes
        ):
            raise ValueError
        if _HEADER_NAME.fullmatch(name) is None or any(
            ord(char) < 0x20 or ord(char) == 0x7F for char in value
        ):
            raise ValueError
        lowered = name.lower()
        if lowered == "content-length":
            lengths.append(value.strip())
        elif lowered == "content-encoding":
            encodings.append(value.strip().lower())
        elif lowered == "transfer-encoding":
            transfer_encodings.append(value.strip().lower())
        elif lowered == "content-type":
            content_types.append(value)
    if len(set(lengths)) > 1 or any(not item.isascii() or not item.isdigit() for item in lengths):
        raise ValueError
    content_length = int(lengths[0]) if lengths else None
    if len(encodings) > 1 or (encodings and encodings[0] != "identity"):
        raise ValueError
    if len(transfer_encodings) > 1 or (transfer_encodings and transfer_encodings[0] != "chunked"):
        raise ValueError
    if transfer_encodings and lengths:
        raise ValueError
    if len(content_types) > 1:
        raise ValueError
    content_type: str | None = None
    if content_types:
        media = content_types[0].split(";", 1)[0].strip().lower()
        if not media.isascii() or _MEDIA_TYPE.fullmatch(media) is None:
            raise ValueError
        content_type = media
    return content_length, content_type, False


def _initial_header_findings(
    response: http.client.HTTPResponse,
    secrets: tuple[bytes, ...],
) -> tuple[bool, bool]:
    raw = getattr(response, "capture_initial_header_bytes", b"")
    invalid = getattr(response, "capture_initial_header_invalid", False) is True
    evidence = raw if type(raw) is bytes else b""
    reflected_during_acquisition = (
        getattr(response, "capture_initial_header_reflection", False) is True
    )
    message = getattr(response, "headers", None)
    defects = getattr(message, "defects", ())
    if message is not None and defects:
        invalid = True
        payload = message.get_payload()
        if type(payload) is str:
            try:
                evidence += payload.encode("iso-8859-1")
            except UnicodeEncodeError:
                invalid = True
    reflected = reflected_during_acquisition or bool(
        secrets and _contains_secret(evidence, secrets)
    )
    return invalid, reflected


def _base_result(
    failure: TransportFailureKind,
    *,
    status: int | None = None,
    outcome: AcquisitionOutcome = AcquisitionOutcome.NOT_STARTED,
) -> TransportResult:
    retention = (
        RetentionState.ABSENT
        if outcome in {AcquisitionOutcome.NOT_STARTED, AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE}
        else RetentionState.PARTIAL
    )
    return TransportResult(failure, status, None, None, outcome, retention, 0, None, None, None)


def _request_material_is_valid(
    target: object,
    authentication_headers: object,
    confidentiality_values: object,
) -> bool:
    if (
        type(target) is not CaptureTarget
        or type(target.position) is not int
        or not 0 <= target.position < 64
    ):
        return False
    try:
        probe_target = CaptureTarget(
            position=0,
            venue=target.venue,
            environment=target.environment,
            origin=target.origin,
            identifier=target.identifier,
            limits=target.limits,
            provenance=target.provenance,
        )
        validate_specification(
            CaptureSpecification(
                CAPTURE_SPECIFICATION_SCHEMA_VERSION,
                "transport/validation",
                (probe_target,),
                target.provenance,
            )
        )
    except Exception:
        return False
    if type(authentication_headers) is not tuple or type(confidentiality_values) is not tuple:
        return False
    if target.venue is Venue.POLYMARKET:
        return authentication_headers == () and confidentiality_values == ()
    if len(authentication_headers) != 3 or len(confidentiality_values) != 2:
        return False
    if any(type(item) is not tuple or len(item) != 2 for item in authentication_headers):
        return False
    key_header, timestamp_header, signature_header = authentication_headers
    expected_names = (
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-TIMESTAMP",
        "KALSHI-ACCESS-SIGNATURE",
    )
    if tuple(item[0] for item in authentication_headers) != expected_names:
        return False
    key_id = key_header[1]
    timestamp = timestamp_header[1]
    signature = signature_header[1]
    signature_valid = False
    if type(signature) is str and 1 <= len(signature) <= 4096 and signature.isascii():
        try:
            decoded = base64.b64decode(signature, validate=True)
            signature_valid = (
                128 <= len(decoded) <= 1024
                and base64.b64encode(decoded).decode("ascii") == signature
            )
        except (ValueError, binascii.Error):
            pass
    return (
        type(key_id) is str
        and _KEY_ID.fullmatch(key_id) is not None
        and type(timestamp) is str
        and _TIMESTAMP.fullmatch(timestamp) is not None
        and signature_valid
        and confidentiality_values == (key_id, signature)
    )


def dispatch(
    target: CaptureTarget,
    authentication_headers: tuple[tuple[str, str], ...] = (),
    *,
    confidentiality_values: tuple[str, ...] = (),
    clock: Clock | None = None,
) -> TransportResult:
    """Perform one direct allowlisted GET dispatch and bounded acquisition."""

    if not _request_material_is_valid(target, authentication_headers, confidentiality_values):
        return _base_result(TransportFailureKind.TRANSPORT)
    selected_clock = clock or _SystemClock()
    parsed = urlsplit(target.origin)
    if (
        target.origin != expected_origin(target.venue, target.environment)
        or parsed.scheme != "https"
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.hostname is None
    ):
        return _base_result(TransportFailureKind.TRANSPORT)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    connection = _DirectHTTPSConnection(
        parsed.hostname,
        parsed.port or 443,
        timeout=min(
            float(target.limits.connect_timeout_seconds),
            float(target.limits.elapsed_budget_seconds),
        ),
        context=context,
    )
    response: http.client.HTTPResponse | None = None
    status: int | None = None
    secrets = tuple(value.encode("ascii") for value in confidentiality_values)
    started = selected_clock.monotonic()
    connection.configure_budget(
        selected_clock,
        started,
        float(target.limits.elapsed_budget_seconds),
        float(target.limits.connect_timeout_seconds),
    )
    try:
        _remaining(selected_clock, started, float(target.limits.elapsed_budget_seconds))
        connection.connect()
        _remaining(selected_clock, started, float(target.limits.elapsed_budget_seconds))
        _set_timeout(
            connection,
            selected_clock,
            started,
            float(target.limits.inactivity_timeout_seconds),
            float(target.limits.elapsed_budget_seconds),
        )
        connection.putrequest(
            "GET", request_path(target), skip_host=True, skip_accept_encoding=True
        )
        connection.putheader("Host", parsed.netloc)
        connection.putheader("Accept", "application/json")
        connection.putheader("Accept-Encoding", "identity")
        connection.putheader("Connection", "close")
        for name, value in authentication_headers:
            connection.putheader(name, value)
        connection.endheaders()
        _remaining(selected_clock, started, float(target.limits.elapsed_budget_seconds))
        _set_timeout(
            connection,
            selected_clock,
            started,
            float(target.limits.inactivity_timeout_seconds),
            float(target.limits.elapsed_budget_seconds),
        )
        configure_headers = getattr(connection, "configure_header_acquisition", None)
        if configure_headers is not None:
            configure_headers(
                secrets,
                float(target.limits.inactivity_timeout_seconds),
            )
        response = connection.getresponse()
        status = response.status if type(response.status) is int else None
        initial_headers_invalid, initial_header_reflection = _initial_header_findings(
            response, secrets
        )
        if initial_header_reflection:
            return TransportResult(
                TransportFailureKind.CONFIDENTIALITY,
                status,
                None,
                None,
                AcquisitionOutcome.NOT_STARTED,
                RetentionState.SUPPRESSED,
                0,
                None,
                None,
                "header",
            )
        if initial_headers_invalid:
            return _base_result(TransportFailureKind.HEADERS, status=status)
        header_failure = getattr(response, "capture_initial_header_failure", None)
        if header_failure in {
            TransportFailureKind.TIMEOUT,
            TransportFailureKind.TRANSPORT,
        }:
            return _base_result(header_failure, status=status)
        try:
            content_length, content_type, header_reflection = _header_metadata(
                response.getheaders(), secrets, target
            )
        except (ValueError, OverflowError):
            return _base_result(TransportFailureKind.HEADERS, status=status)
        if header_reflection:
            return TransportResult(
                TransportFailureKind.CONFIDENTIALITY,
                status,
                None,
                None,
                AcquisitionOutcome.NOT_STARTED,
                RetentionState.SUPPRESSED,
                0,
                None,
                None,
                "header",
            )
        if content_length is not None and content_length > target.limits.max_body_bytes:
            return TransportResult(
                TransportFailureKind.OVERSIZED,
                status,
                content_length,
                content_type,
                AcquisitionOutcome.NOT_STARTED,
                RetentionState.ABSENT,
                0,
                None,
                None,
                None,
            )
        _remaining(selected_clock, started, float(target.limits.elapsed_budget_seconds))
        body = bytearray()
        try:
            while True:
                _set_timeout(
                    connection,
                    selected_clock,
                    started,
                    float(target.limits.inactivity_timeout_seconds),
                    float(target.limits.elapsed_budget_seconds),
                )
                remaining_cap = target.limits.max_body_bytes + 1 - len(body)
                chunk = response.read(min(target.limits.body_chunk_bytes, remaining_cap))
                if chunk:
                    body.extend(chunk)
                trailer_failure = getattr(response, "capture_trailer_failure", None)
                if trailer_failure is TransportFailureKind.TIMEOUT:
                    raise _BudgetExceeded
                if trailer_failure is TransportFailureKind.TRANSPORT:
                    raise OSError("trailer consumption failed")
                _remaining(selected_clock, started, float(target.limits.elapsed_budget_seconds))
                if chunk:
                    if content_length is not None and len(body) > content_length:
                        raise OSError("response exceeded declared Content-Length")
                    if len(body) > target.limits.max_body_bytes:
                        prefix = bytes(body[: target.limits.max_body_bytes])
                        if secrets and _contains_secret(prefix, secrets):
                            return TransportResult(
                                TransportFailureKind.CONFIDENTIALITY,
                                status,
                                None,
                                None,
                                AcquisitionOutcome.OVERSIZED,
                                RetentionState.SUPPRESSED,
                                len(body),
                                None,
                                None,
                                "body",
                            )
                        return TransportResult(
                            TransportFailureKind.OVERSIZED,
                            status,
                            content_length,
                            content_type,
                            AcquisitionOutcome.OVERSIZED,
                            RetentionState.OVERSIZED,
                            len(body),
                            prefix,
                            hashlib.sha256(prefix).hexdigest(),
                            None,
                        )
                    if content_length is not None and len(body) == content_length:
                        complete = bytes(body)
                        if secrets and _contains_secret(complete, secrets):
                            return TransportResult(
                                TransportFailureKind.CONFIDENTIALITY,
                                status,
                                None,
                                None,
                                AcquisitionOutcome.COMPLETED,
                                RetentionState.SUPPRESSED,
                                len(complete),
                                None,
                                None,
                                "body",
                            )
                        return TransportResult(
                            None,
                            status,
                            content_length,
                            content_type,
                            AcquisitionOutcome.COMPLETED,
                            RetentionState.COMPLETE,
                            len(complete),
                            complete,
                            hashlib.sha256(complete).hexdigest(),
                            None,
                        )
                    continue
                if content_length is not None and len(body) != content_length:
                    raise OSError("response ended before declared Content-Length")
                complete = bytes(body)
                if secrets and _contains_secret(complete, secrets):
                    return TransportResult(
                        TransportFailureKind.CONFIDENTIALITY,
                        status,
                        None,
                        None,
                        AcquisitionOutcome.COMPLETED,
                        RetentionState.SUPPRESSED,
                        len(complete),
                        None,
                        None,
                        "body",
                    )
                return TransportResult(
                    None,
                    status,
                    content_length,
                    content_type,
                    AcquisitionOutcome.COMPLETED,
                    RetentionState.COMPLETE,
                    len(complete),
                    complete,
                    hashlib.sha256(complete).hexdigest(),
                    None,
                )
        except _ChunkedReadFailure as exc:
            body.extend(exc.partial)
            failure = TransportFailureKind.PARTIAL if body else exc.failure
        except (TimeoutError, _BudgetExceeded):
            failure = TransportFailureKind.PARTIAL if body else TransportFailureKind.TIMEOUT
        except http.client.IncompleteRead as exc:
            body.extend(exc.partial)
            failure = TransportFailureKind.PARTIAL if body else TransportFailureKind.TRANSPORT
        except (OSError, http.client.HTTPException, ssl.SSLError):
            failure = TransportFailureKind.PARTIAL if body else TransportFailureKind.TRANSPORT
        prefix = bytes(body)
        if len(prefix) > target.limits.max_body_bytes:
            retained = prefix[: target.limits.max_body_bytes]
            if secrets and _contains_secret(retained, secrets):
                return TransportResult(
                    TransportFailureKind.CONFIDENTIALITY,
                    status,
                    None,
                    None,
                    AcquisitionOutcome.OVERSIZED,
                    RetentionState.SUPPRESSED,
                    target.limits.max_body_bytes + 1,
                    None,
                    None,
                    "body",
                )
            return TransportResult(
                TransportFailureKind.OVERSIZED,
                status,
                content_length,
                content_type,
                AcquisitionOutcome.OVERSIZED,
                RetentionState.OVERSIZED,
                target.limits.max_body_bytes + 1,
                retained,
                hashlib.sha256(retained).hexdigest(),
                None,
            )
        if prefix:
            if secrets and _contains_secret(prefix, secrets):
                return TransportResult(
                    TransportFailureKind.CONFIDENTIALITY,
                    status,
                    None,
                    None,
                    AcquisitionOutcome.PARTIAL,
                    RetentionState.SUPPRESSED,
                    len(prefix),
                    None,
                    None,
                    "body",
                )
            return TransportResult(
                failure,
                status,
                content_length,
                content_type,
                AcquisitionOutcome.PARTIAL,
                RetentionState.PARTIAL,
                len(prefix),
                prefix,
                hashlib.sha256(prefix).hexdigest(),
                None,
            )
        return TransportResult(
            failure,
            status,
            content_length,
            content_type,
            AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
            RetentionState.ABSENT,
            0,
            None,
            None,
            None,
        )
    except (TimeoutError, _BudgetExceeded):
        return _base_result(TransportFailureKind.TIMEOUT, status=status)
    except (OSError, http.client.HTTPException, ssl.SSLError, ValueError):
        return _base_result(TransportFailureKind.TRANSPORT, status=status)
    finally:
        if response is not None:
            response.close()
        connection.close()


__all__ = ["TransportFailureKind", "TransportResult", "dispatch"]
