from __future__ import annotations

import hashlib
import io
import socket

import pytest

import invariant_engine.capture.transport as transport_module
from conftest import SIGNATURE, kalshi_target, polymarket_target
from invariant_engine.capture import AcquisitionOutcome, RetentionState, TransportFailureKind


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers=None, failure=None):
        self.status = status
        self._body = body
        self._position = 0
        self._headers = headers or [("Content-Type", "application/json")]
        self._failure = failure

    def getheaders(self):
        return self._headers

    def read(self, amount: int) -> bytes:
        if self._failure is not None:
            failure, after = self._failure
            if self._position >= after:
                raise failure
        result = self._body[self._position : self._position + amount]
        self._position += len(result)
        return result

    def close(self) -> None:
        pass


class FakeConnection:
    response = FakeResponse(b"{}")
    instances = []

    def __init__(self, host, port, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.sock = None
        self.calls = []
        self.__class__.instances.append(self)

    def connect(self):
        self.calls.append(("connect",))

    def configure_budget(self, clock, started, budget, operation_timeout):
        self.calls.append(("budget", started, budget, operation_timeout))

    def putrequest(self, *args, **kwargs):
        self.calls.append(("request", args, kwargs))

    def putheader(self, *args):
        self.calls.append(("header", args))

    def endheaders(self):
        self.calls.append(("end",))

    def getresponse(self):
        return self.response

    def close(self):
        self.calls.append(("close",))


class SyntheticClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


class DeadlineResponse(FakeResponse):
    def __init__(
        self,
        chunks: tuple[bytes, ...],
        clock: SyntheticClock,
        *,
        expire_on_read: int,
    ) -> None:
        super().__init__(b"")
        self._chunks = iter(chunks)
        self._clock = clock
        self._read_count = 0
        self._expire_on_read = expire_on_read

    def read(self, amount: int) -> bytes:
        chunk = next(self._chunks, b"")
        assert len(chunk) <= amount
        self._read_count += 1
        if self._read_count == self._expire_on_read:
            self._clock.now = 20.1
        return chunk


class SocketBytes:
    def __init__(self, wire: bytes) -> None:
        self.wire = wire

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.wire)


class HeaderStream(io.BytesIO):
    def __init__(
        self,
        wire: bytes,
        clock: SyntheticClock,
        *,
        tick: float = 0.0,
        tick_after_call: int = 0,
        failure: tuple[BaseException, int] | None = None,
        readline_ticks: dict[int, float] | None = None,
        read_ticks: dict[int, float] | None = None,
    ) -> None:
        super().__init__(wire)
        self.clock = clock
        self.tick = tick
        self.tick_after_call = tick_after_call
        self.failure = failure
        self.readline_ticks = readline_ticks or {}
        self.read_ticks = read_ticks or {}
        self.readline_calls = 0
        self.read_calls = 0
        self.read_sizes: list[int] = []
        self.bytes_returned = 0

    def readline(self, size: int = -1) -> bytes:
        self.readline_calls += 1
        if self.failure is not None and self.readline_calls == self.failure[1]:
            raise self.failure[0]
        if self.readline_ticks:
            self.clock.now += self.readline_ticks.get(self.readline_calls, 0.0)
        elif self.readline_calls > self.tick_after_call:
            self.clock.now += self.tick
        result = super().readline(size)
        self.bytes_returned += len(result)
        return result

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        self.read_sizes.append(size)
        self.clock.now += self.read_ticks.get(self.read_calls, 0.0)
        result = super().read(size)
        self.bytes_returned += len(result)
        return result


class RawSocket:
    def __init__(self, stream: HeaderStream) -> None:
        self.stream = stream
        self.timeouts: list[float] = []

    def makefile(self, *args, **kwargs):
        return self.stream

    def settimeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)

    def sendall(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


class WireConnection(FakeConnection):
    wire = b""

    def getresponse(self):
        response = transport_module._StrictHTTPResponse(SocketBytes(self.wire), method="GET")
        response.begin()
        return response


def run(monkeypatch, response: FakeResponse, target=None, headers=(), **kwargs):
    FakeConnection.response = response
    FakeConnection.instances = []
    monkeypatch.setattr(transport_module, "_DirectHTTPSConnection", FakeConnection)
    return transport_module.dispatch(target or polymarket_target(), headers, **kwargs)


def run_wire(monkeypatch, wire: bytes, target=None, headers=(), **kwargs):
    WireConnection.wire = wire
    WireConnection.instances = []
    monkeypatch.setattr(transport_module, "_DirectHTTPSConnection", WireConnection)
    return transport_module.dispatch(target or polymarket_target(), headers, **kwargs)


def run_production_wire(
    monkeypatch,
    wire: bytes,
    target=None,
    headers=(),
    *,
    confidentiality_values=(),
    tick: float = 0.0,
    tick_after_call: int = 0,
    failure: tuple[BaseException, int] | None = None,
    readline_ticks: dict[int, float] | None = None,
    read_ticks: dict[int, float] | None = None,
):
    clock = SyntheticClock()
    stream = HeaderStream(
        wire,
        clock,
        tick=tick,
        tick_after_call=tick_after_call,
        failure=failure,
        readline_ticks=readline_ticks,
        read_ticks=read_ticks,
    )
    raw_socket = RawSocket(stream)

    def connect(connection) -> None:
        connection.sock = raw_socket

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    result = transport_module.dispatch(
        target or polymarket_target(),
        headers,
        confidentiality_values=confidentiality_values,
        clock=clock,
    )
    return result, stream, raw_socket


def chunked_wire(body: bytes, trailer_section: bytes = b"\r\n") -> bytes:
    encoded_body = b""
    if body:
        encoded_body = f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n"
    return (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n" + encoded_body + b"0\r\n" + trailer_section
    )


def trailer_line(length: int, byte: bytes = b"x") -> bytes:
    assert length >= 4
    return b"X:" + (byte * (length - 4)) + b"\r\n"


def test_exact_request_headers_and_tls_policy(monkeypatch) -> None:
    result = run(monkeypatch, FakeResponse(b"{}"))
    connection = FakeConnection.instances[0]
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert (
        "request",
        ("GET", "/book?token_id=123"),
        {"skip_host": True, "skip_accept_encoding": True},
    ) in connection.calls
    sent = [call[1] for call in connection.calls if call[0] == "header"]
    assert sent == [
        ("Host", "clob.polymarket.com"),
        ("Accept", "application/json"),
        ("Accept-Encoding", "identity"),
        ("Connection", "close"),
    ]
    assert connection.context.check_hostname is True


def test_low_level_connection_uses_first_dns_address_and_verified_tls(monkeypatch) -> None:
    events = []

    class RawSocket:
        def settimeout(self, value):
            events.append(("timeout", value))

        def connect(self, address):
            events.append(("connect", address))

        def close(self):
            events.append(("close",))

    class Context:
        verify_mode = transport_module.ssl.CERT_REQUIRED
        check_hostname = True

        def wrap_socket(self, raw, server_hostname):
            events.append(("tls", server_hostname))
            return raw

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("192.0.2.1", 443)), (2, 1, 6, "", ("192.0.2.2", 443))],
    )
    monkeypatch.setattr(socket, "socket", lambda *a: RawSocket())
    connection = transport_module._DirectHTTPSConnection(
        "example.test", 443, timeout=5, context=Context()
    )
    connection.connect()
    assert ("connect", ("192.0.2.1", 443)) in events
    assert ("connect", ("192.0.2.2", 443)) not in events
    assert ("tls", "example.test") in events


def test_header_limits_encoding_and_conflicts_fail_before_body(monkeypatch) -> None:
    for headers in (
        [("Content-Encoding", "gzip")],
        [("Content-Length", "1"), ("Content-Length", "2")],
        [("Transfer-Encoding", "chunked"), ("Content-Length", "1")],
        [("Bad Header", "x")],
    ):
        result = run(monkeypatch, FakeResponse(b"x", headers=headers))
        assert result.failure is TransportFailureKind.HEADERS
        assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED


@pytest.mark.parametrize(
    "header_block",
    (
        b"Bad Header: x\r\n",
        b"Good: first\r\nMalformed field\r\nX-After: visible\r\n",
    ),
)
def test_raw_initial_malformed_headers_fail_before_body(monkeypatch, header_block: bytes) -> None:
    result = run_wire(monkeypatch, b"HTTP/1.1 200 OK\r\n" + header_block + b"\r\n{}")
    assert result.failure is TransportFailureKind.HEADERS
    assert result.http_status == 200
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


@pytest.mark.parametrize("reflected_secret", ("synthetic-key-7", SIGNATURE))
def test_raw_initial_malformed_headers_preserve_confidentiality_evidence(
    monkeypatch, reflected_secret: str
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    wire = (
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nBad Header: x\r\n"
        + b"X-Reflection: "
        + reflected_secret.encode("ascii")
        + b"\r\n\r\n{}"
    )
    result = run_wire(
        monkeypatch,
        wire,
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.http_status == 200
    assert result.content_length is None
    assert result.content_type is None
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.suppression_source == "header"


def test_raw_initial_valid_headers_reach_body_acquisition(monkeypatch) -> None:
    body = b"{}"
    result = run_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
        b"Content-Type: application/json; charset=utf-8\r\nX-Unknown: visible\r\n\r\n" + body,
    )
    assert result.failure is None
    assert result.content_length == len(body)
    assert result.content_type == "application/json"
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retained_body == body


def test_raw_initial_header_field_bound_accepts_100_and_rejects_101(monkeypatch) -> None:
    accepted_headers = b"".join(f"X-{index}: v\r\n".encode() for index in range(99))
    accepted = run_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\n" + accepted_headers + b"Content-Length: 2\r\n\r\n{}",
    )
    rejected_headers = b"".join(f"X-{index}: v\r\n".encode() for index in range(101))
    rejected = run_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\n" + rejected_headers + b"\r\n{}",
    )
    assert accepted.failure is None
    assert accepted.retained_body == b"{}"
    assert rejected.failure is TransportFailureKind.HEADERS
    assert rejected.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert rejected.received_byte_count == 0


def test_informational_headers_use_cumulative_bounds(monkeypatch) -> None:
    interim = b"HTTP/1.1 100 Continue\r\nX-Pad: " + (b"x" * 1000) + b"\r\n\r\n"
    final = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    result, stream, _ = run_production_wire(monkeypatch, (interim * 40) + final)
    assert result.failure is TransportFailureKind.HEADERS
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert stream.readline_calls < 123


def test_valid_informational_response_sequence_reaches_body(monkeypatch) -> None:
    wire = (
        b"HTTP/1.1 100 Continue\r\nX-Interim: visible\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    )
    result, _, _ = run_production_wire(monkeypatch, wire)
    assert result.failure is None
    assert result.http_status == 200
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retained_body == b"{}"


def test_header_reads_stop_at_elapsed_budget_and_reduce_timeout(monkeypatch) -> None:
    headers = b"".join(b"X-Pad: x\r\n" for _ in range(50))
    result, stream, raw_socket = run_production_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n{}",
        tick=1.0,
    )
    assert result.failure is TransportFailureKind.TIMEOUT
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert stream.readline_calls <= 20
    assert min(raw_socket.timeouts) == 1.0


@pytest.mark.parametrize("interruption", (TimeoutError("timeout"), OSError("failure")))
@pytest.mark.parametrize("reflected_secret", ("synthetic-key-7", SIGNATURE))
def test_interrupted_headers_preserve_received_authentication_reflection(
    monkeypatch, interruption: BaseException, reflected_secret: str
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    result, _, _ = run_production_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nX-Reflection: " + reflected_secret.encode("ascii") + b"\r\n",
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
        failure=(interruption, 3),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.http_status == 200
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.suppression_source == "header"


@pytest.mark.parametrize(
    ("interruption", "expected"),
    (
        (TimeoutError("timeout"), TransportFailureKind.TIMEOUT),
        (OSError("failure"), TransportFailureKind.TRANSPORT),
    ),
)
def test_interrupted_nonsecret_headers_fail_without_body_acquisition(
    monkeypatch,
    interruption: BaseException,
    expected: TransportFailureKind,
) -> None:
    result, _, _ = run_production_wire(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nX-Visible: ordinary\r\n",
        failure=(interruption, 3),
    )
    assert result.failure is expected
    assert result.http_status == 200
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


@pytest.mark.parametrize(
    ("interruption", "expected_failure"),
    (
        (TimeoutError("chunk marker timeout"), TransportFailureKind.PARTIAL),
        (OSError("chunk marker failure"), TransportFailureKind.PARTIAL),
    ),
)
def test_interruption_between_chunks_preserves_body_from_unfinished_read(
    monkeypatch,
    interruption: BaseException,
    expected_failure: TransportFailureKind,
) -> None:
    body = b"first-chunk-15"
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body),
        failure=(interruption, 6),
    )
    assert result.failure is expected_failure
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.PARTIAL
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()


def test_repeated_small_chunks_enforce_budget_and_shrink_timeouts(monkeypatch) -> None:
    encoded = b"1\r\nx\r\n" * 100
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n" + encoded + b"0\r\n\r\n"
    )
    result, stream, raw_socket = run_production_wire(monkeypatch, wire, tick=1.0)
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == 15
    assert result.retained_body == b"x" * 15
    assert result.retained_body_sha256 == hashlib.sha256(b"x" * 15).hexdigest()
    assert stream.readline_calls == 20
    assert stream.read_calls == 30
    assert stream.clock.now == 20.0
    assert min(raw_socket.timeouts) == 1.0


@pytest.mark.parametrize(
    ("readline_ticks", "read_ticks", "expected_body", "line_reads", "data_reads"),
    (
        ({5: 20.1}, {}, b"", 5, 0),
        ({}, {1: 20.1}, b"x", 5, 1),
        ({}, {2: 20.1}, b"x", 5, 2),
        ({6: 20.1}, {}, b"x", 6, 2),
    ),
)
def test_deadline_crossing_each_chunk_read_stage_stops_further_io(
    monkeypatch,
    readline_ticks: dict[int, float],
    read_ticks: dict[int, float],
    expected_body: bytes,
    line_reads: int,
    data_reads: int,
) -> None:
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n"
        b"1\r\nx\r\n1\r\ny\r\n0\r\n\r\n"
    )
    result, stream, _ = run_production_wire(
        monkeypatch,
        wire,
        readline_ticks=readline_ticks,
        read_ticks=read_ticks,
    )
    assert result.failure is (
        TransportFailureKind.PARTIAL if expected_body else TransportFailureKind.TIMEOUT
    )
    assert result.acquisition_outcome is (
        AcquisitionOutcome.PARTIAL if expected_body else AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    )
    assert result.received_byte_count == len(expected_body)
    assert result.retained_body == (expected_body or None)
    assert result.retained_body_sha256 == (
        hashlib.sha256(expected_body).hexdigest() if expected_body else None
    )
    assert stream.readline_calls == line_reads
    assert stream.read_calls == data_reads
    assert stream.clock.now == 20.1


def test_deadline_crossing_entity_read_combines_existing_prefix_once(monkeypatch) -> None:
    body = (b"a" * 65_536) + b"deadline-tail"
    result, stream, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body),
        read_ticks={2: 20.1},
    )
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()
    assert stream.read_calls == 2
    assert stream.readline_calls == 5


@pytest.mark.parametrize(
    ("interruption", "expected_failure"),
    (
        (TimeoutError("first chunk timeout"), TransportFailureKind.TIMEOUT),
        (OSError("first chunk failure"), TransportFailureKind.TRANSPORT),
    ),
)
def test_interruption_before_first_chunk_preserves_zero_byte_classification(
    monkeypatch,
    interruption: BaseException,
    expected_failure: TransportFailureKind,
) -> None:
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(b"first"),
        failure=(interruption, 5),
    )
    assert result.failure is expected_failure
    assert result.acquisition_outcome is AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


@pytest.mark.parametrize(
    ("wire_body", "expected_body"),
    (
        (b"-1\r\n", b""),
        (b"3\r\nabc\r\n-1\r\n", b"abc"),
    ),
)
def test_negative_chunk_length_fails_before_unbounded_entity_read(
    monkeypatch, wire_body: bytes, expected_body: bytes
) -> None:
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n" + wire_body
    )
    result, stream, _ = run_production_wire(monkeypatch, wire)
    assert result.failure is (
        TransportFailureKind.PARTIAL if expected_body else TransportFailureKind.TRANSPORT
    )
    assert result.acquisition_outcome is (
        AcquisitionOutcome.PARTIAL if expected_body else AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    )
    assert result.received_byte_count == len(expected_body)
    assert result.retention_state is (
        RetentionState.PARTIAL if expected_body else RetentionState.ABSENT
    )
    assert result.retained_body == (expected_body or None)
    assert result.retained_body_sha256 == (
        hashlib.sha256(expected_body).hexdigest() if expected_body else None
    )
    assert all(0 < size <= 65_536 for size in stream.read_sizes)


@pytest.mark.parametrize(
    ("wire_body", "expected_body"),
    (
        (b"0\r\n\r\n", b""),
        (b"3\r\nabc\r\n0\r\n\r\n", b"abc"),
    ),
)
def test_zero_and_positive_chunk_lengths_remain_bounded_controls(
    monkeypatch, wire_body: bytes, expected_body: bytes
) -> None:
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n" + wire_body
    )
    result, stream, _ = run_production_wire(monkeypatch, wire)
    assert result.failure is None
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retention_state is RetentionState.COMPLETE
    assert result.received_byte_count == len(expected_body)
    assert result.retained_body == expected_body
    assert result.retained_body_sha256 == hashlib.sha256(expected_body).hexdigest()
    assert all(0 < size <= 65_536 for size in stream.read_sizes)


def test_chunk_interruption_combines_existing_and_unfinished_read_prefixes_once(
    monkeypatch,
) -> None:
    body = (b"a" * 65_536) + b"second-part"
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body),
        failure=(TimeoutError("next chunk marker"), 6),
    )
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize(
    ("declared_size", "wire_body", "expected_body"),
    (
        (10, b"abc", b"abc"),
        (3, b"abc\r", b"abc"),
    ),
)
def test_premature_chunk_eof_preserves_entity_bytes_but_not_framing(
    monkeypatch,
    declared_size: int,
    wire_body: bytes,
    expected_body: bytes,
) -> None:
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n"
        + f"{declared_size:x}\r\n".encode("ascii")
        + wire_body
    )
    result, _, _ = run_production_wire(monkeypatch, wire)
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(expected_body)
    assert result.retained_body == expected_body
    assert result.retained_body_sha256 == hashlib.sha256(expected_body).hexdigest()


@pytest.mark.parametrize("body", (b"synthetic-key-7", SIGNATURE.encode("ascii")))
def test_reflected_body_from_interrupted_chunk_read_has_confidentiality_precedence(
    monkeypatch, body: bytes
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
        failure=(TimeoutError("chunk marker timeout"), 6),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.suppression_source == "body"


def test_reflected_deadline_crossing_entity_read_has_confidentiality_precedence(
    monkeypatch,
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = b"synthetic-key-7"
    result, stream, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
        read_ticks={1: 20.1},
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.suppression_source == "body"
    assert stream.read_calls == 1


@pytest.mark.parametrize(
    ("body", "trailer_section"),
    (
        (b"", b"\r\n"),
        (b"{}", b"\r\n"),
        (b"", b"X-Discarded: value\r\n\r\n"),
        (b"{}", b"X-Discarded: value\r\nAnother: field\r\n\r\n"),
    ),
)
def test_chunked_empty_and_nonempty_trailers_complete_without_publication(
    monkeypatch, body: bytes, trailer_section: bytes
) -> None:
    result, _, _ = run_production_wire(monkeypatch, chunked_wire(body, trailer_section))
    assert result.failure is None
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retention_state is RetentionState.COMPLETE
    assert result.received_byte_count == len(body)
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()
    assert result.content_length is None
    assert result.content_type == "application/json"
    assert "X-Discarded" not in repr(result)
    assert "Another" not in repr(result)


@pytest.mark.parametrize("reflected_secret", ("synthetic-key-7", SIGNATURE))
def test_trailer_only_authentication_reflection_is_discarded_without_suppression(
    monkeypatch, reflected_secret: str
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    trailer_section = (
        b"Content-Type: text/plain\r\nContent-Length: 999\r\nX-Reflection: "
        + reflected_secret.encode("ascii")
        + b"\r\n\r\n"
    )
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(b"{}", trailer_section),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is None
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retention_state is RetentionState.COMPLETE
    assert result.retained_body == b"{}"
    assert result.content_length is None
    assert result.content_type == "application/json"
    assert reflected_secret not in repr(result)


@pytest.mark.parametrize(
    "trailer_section",
    (
        trailer_line(8_192) + b"\r\n",
        (b"X:\r\n" * 100) + b"\r\n",
        (trailer_line(8_192) * 3) + trailer_line(8_190) + b"\r\n",
    ),
)
def test_trailer_limits_accept_exact_boundaries(monkeypatch, trailer_section: bytes) -> None:
    result, _, _ = run_production_wire(monkeypatch, chunked_wire(b"", trailer_section))
    assert result.failure is None
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.retained_body == b""
    assert result.retained_body_sha256 == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize(
    "trailer_section",
    (
        trailer_line(8_193) + b"\r\n",
        (b"X:\r\n" * 101) + b"\r\n",
        (trailer_line(8_192) * 3) + trailer_line(8_191) + b"\r\n",
    ),
)
def test_trailer_limits_reject_bounded_excess(monkeypatch, trailer_section: bytes) -> None:
    wire = chunked_wire(b"", trailer_section) + (b"unread-sentinel" * 1_000)
    result, stream, _ = run_production_wire(monkeypatch, wire)
    assert result.failure is TransportFailureKind.TRANSPORT
    assert result.acquisition_outcome is AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert stream.bytes_returned < len(wire)


def test_repeated_trailer_reads_enforce_elapsed_budget_and_shrink_timeout(
    monkeypatch,
) -> None:
    trailer_section = (b"X: value\r\n" * 30) + b"\r\n"
    result, stream, raw_socket = run_production_wire(
        monkeypatch,
        chunked_wire(b"", trailer_section),
        tick=1.0,
        tick_after_call=5,
    )
    assert result.failure is TransportFailureKind.TIMEOUT
    assert result.acquisition_outcome is AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    assert result.received_byte_count == 0
    assert result.retention_state is RetentionState.ABSENT
    assert stream.readline_calls == 25
    assert min(raw_socket.timeouts) == 1.0


@pytest.mark.parametrize(
    ("body", "interruption", "expected_failure"),
    (
        (b"", TimeoutError("inactivity"), TransportFailureKind.TIMEOUT),
        (b"", OSError("transport detail must not escape"), TransportFailureKind.TRANSPORT),
        (b"prefix", TimeoutError("inactivity"), TransportFailureKind.PARTIAL),
        (b"prefix", OSError("transport detail must not escape"), TransportFailureKind.PARTIAL),
    ),
)
def test_interrupted_trailer_reads_preserve_entity_body_facts(
    monkeypatch,
    body: bytes,
    interruption: BaseException,
    expected_failure: TransportFailureKind,
) -> None:
    trailer_read_call = 6 if not body else 7
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body, b"X: unread\r\n\r\n"),
        failure=(interruption, trailer_read_call),
    )
    expected_outcome = (
        AcquisitionOutcome.PARTIAL if body else AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    )
    expected_retention = RetentionState.PARTIAL if body else RetentionState.ABSENT
    assert result.failure is expected_failure
    assert result.acquisition_outcome is expected_outcome
    assert result.received_byte_count == len(body)
    assert result.retention_state is expected_retention
    assert result.retained_body == (body or None)
    assert result.retained_body_sha256 == (hashlib.sha256(body).hexdigest() if body else None)
    assert "transport detail" not in repr(result)
    assert "inactivity" not in repr(result)


@pytest.mark.parametrize("body", (b"", b"prefix"))
def test_unterminated_trailers_never_complete_and_preserve_body_prefix(
    monkeypatch, body: bytes
) -> None:
    result, _, _ = run_production_wire(monkeypatch, chunked_wire(body, b"X: no-terminator\r\n"))
    assert result.failure is (
        TransportFailureKind.PARTIAL if body else TransportFailureKind.TRANSPORT
    )
    assert result.acquisition_outcome is (
        AcquisitionOutcome.PARTIAL if body else AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    )
    assert result.received_byte_count == len(body)
    assert result.retained_body == (body or None)
    assert result.retained_body_sha256 == (hashlib.sha256(body).hexdigest() if body else None)


def test_body_confidentiality_precedes_trailer_failure(monkeypatch) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "key-1"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = b'{"secret":"key-1"}'
    result, _, _ = run_production_wire(
        monkeypatch,
        chunked_wire(body, b""),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("key-1", SIGNATURE),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.suppression_source == "body"


def test_empty_partial_oversized_and_digest_scope(monkeypatch) -> None:
    empty = run(monkeypatch, FakeResponse(b"", headers=[("Content-Length", "0")]))
    assert empty.retention_state is RetentionState.COMPLETE
    assert empty.retained_body_sha256 == hashlib.sha256(b"").hexdigest()
    partial = run(monkeypatch, FakeResponse(b"abc", failure=(TimeoutError(), 3)))
    assert partial.failure is TransportFailureKind.PARTIAL
    assert partial.retained_body == b"abc"
    oversized_body = b"x" * 1_048_577
    oversized = run(monkeypatch, FakeResponse(oversized_body))
    assert oversized.received_byte_count == 1_048_577
    assert len(oversized.retained_body or b"") == 1_048_576


def test_declared_oversize_stops_before_body(monkeypatch) -> None:
    result = run(monkeypatch, FakeResponse(b"secret", headers=[("Content-Length", "1048577")]))
    assert result.failure is TransportFailureKind.OVERSIZED
    assert result.acquisition_outcome is AcquisitionOutcome.NOT_STARTED


def test_header_body_raw_and_json_escaped_secret_reflection(monkeypatch) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "key-1"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    header = run(
        monkeypatch,
        FakeResponse(b"ignored", headers=[("X-Reflection", "key-1")]),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("key-1", SIGNATURE),
    )
    assert header.retention_state is RetentionState.SUPPRESSED
    assert header.suppression_source == "header"
    body = run(
        monkeypatch,
        FakeResponse(b'{"x":"key\\u002d1"}'),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("key-1", SIGNATURE),
    )
    assert body.retention_state is RetentionState.SUPPRESSED
    assert body.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert body.retained_body is None


def escaped_first_character(value: str) -> bytes:
    return f"\\u{ord(value[0]):04x}{value[1:]}".encode("ascii")


@pytest.mark.parametrize("surrogate", (b"\\ud800", b"\\udc00"))
@pytest.mark.parametrize("reflected_secret", ("synthetic-key-7", SIGNATURE))
def test_completed_surrogate_token_does_not_hide_later_escaped_authentication_material(
    monkeypatch, surrogate: bytes, reflected_secret: str
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = (
        b'{"bad":"'
        + surrogate
        + b'","secret":"'
        + escaped_first_character(reflected_secret)
        + b'"}'
    )
    wire = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
        + str(len(body)).encode("ascii")
        + b"\r\n\r\n"
        + body
    )
    result, _, _ = run_production_wire(
        monkeypatch,
        wire,
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.http_status == 200
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None
    assert result.content_length is None
    assert result.content_type is None


@pytest.mark.parametrize("surrogate", (b"\\ud800", b"\\udc00"))
def test_completed_nonsecret_surrogate_body_preserves_acquisition(
    monkeypatch, surrogate: bytes
) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = b'{"bad":"' + surrogate + b'","ordinary":"value"}'
    wire = (
        b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    )
    result, _, _ = run_production_wire(
        monkeypatch,
        wire,
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is None
    assert result.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.COMPLETE
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()


def test_partial_surrogate_body_scans_later_escaped_key(monkeypatch) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = b'{"bad":"\\ud800","secret":"synthetic\\u002dkey-7"}'
    result = run(
        monkeypatch,
        FakeResponse(body, failure=(TimeoutError(), len(body))),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


def test_oversized_surrogate_body_scans_later_escaped_signature(monkeypatch) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    prefix = b'{"bad":"\\udc00","secret":"' + escaped_first_character(SIGNATURE) + b'","padding":"'
    body = prefix + (b"x" * (1_048_577 - len(prefix)))
    result = run(
        monkeypatch,
        FakeResponse(body),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.OVERSIZED
    assert result.received_byte_count == 1_048_577
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


def test_anonymous_kalshi_and_polymarket_authentication_are_rejected_before_dispatch(
    monkeypatch,
) -> None:
    FakeConnection.instances = []
    monkeypatch.setattr(transport_module, "_DirectHTTPSConnection", FakeConnection)
    anonymous = transport_module.dispatch(kalshi_target())
    injected = transport_module.dispatch(
        polymarket_target(),
        (("KALSHI-ACCESS-KEY", "key-1"),),
        confidentiality_values=("key-1", SIGNATURE),
    )
    assert anonymous.failure is TransportFailureKind.TRANSPORT
    assert injected.failure is TransportFailureKind.TRANSPORT
    assert FakeConnection.instances == []


def test_identical_content_lengths_are_unambiguous_and_header_count_is_bounded(
    monkeypatch,
) -> None:
    accepted = run(
        monkeypatch,
        FakeResponse(b"{}", headers=[("Content-Length", "2"), ("Content-Length", "2")]),
    )
    assert accepted.failure is None
    rejected = run(monkeypatch, FakeResponse(b"", headers=[(f"X-{i}", "v") for i in range(101)]))
    assert rejected.failure is TransportFailureKind.HEADERS


def test_failure_before_first_byte_records_started_acquisition(monkeypatch) -> None:
    result = run(monkeypatch, FakeResponse(b"", failure=(TimeoutError(), 0)))
    assert result.failure is TransportFailureKind.TIMEOUT
    assert result.acquisition_outcome is AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    assert result.received_byte_count == 0


def test_post_read_deadline_accounts_nonsecret_chunk_before_failure(monkeypatch) -> None:
    clock = SyntheticClock()
    body = b"ordinary bytes"
    result = run(
        monkeypatch,
        DeadlineResponse((body,), clock, expire_on_read=1),
        clock=clock,
    )
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.PARTIAL
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize("reflected_secret", ("synthetic-key-7", SIGNATURE))
def test_post_read_deadline_suppresses_reflected_authentication_material(
    monkeypatch, reflected_secret: str
) -> None:
    clock = SyntheticClock()
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "synthetic-key-7"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    body = reflected_secret.encode("ascii")
    result = run(
        monkeypatch,
        DeadlineResponse((body,), clock, expire_on_read=1),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("synthetic-key-7", SIGNATURE),
        clock=clock,
    )
    assert result.failure is TransportFailureKind.CONFIDENTIALITY
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.SUPPRESSED
    assert result.retained_body is None
    assert result.retained_body_sha256 is None


def test_post_read_deadline_accounts_chunk_after_existing_prefix(monkeypatch) -> None:
    clock = SyntheticClock()
    prefix = b"existing-prefix:"
    final_chunk = b"deadline-chunk"
    body = prefix + final_chunk
    result = run(
        monkeypatch,
        DeadlineResponse((prefix, final_chunk), clock, expire_on_read=2),
        clock=clock,
    )
    assert result.failure is TransportFailureKind.PARTIAL
    assert result.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.received_byte_count == len(body)
    assert result.retention_state is RetentionState.PARTIAL
    assert result.retained_body == body
    assert result.retained_body_sha256 == hashlib.sha256(body).hexdigest()


def test_partial_and_oversized_confidentiality_discard_retained_material(monkeypatch) -> None:
    authentication_headers = (
        ("KALSHI-ACCESS-KEY", "key-1"),
        ("KALSHI-ACCESS-TIMESTAMP", "1"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )
    partial = run(
        monkeypatch,
        FakeResponse(b"prefix-key-1", failure=(TimeoutError(), 12)),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("key-1", SIGNATURE),
    )
    oversized = run(
        monkeypatch,
        FakeResponse(b"key-1" + b"x" * 1_048_572),
        target=kalshi_target(),
        headers=authentication_headers,
        confidentiality_values=("key-1", SIGNATURE),
    )
    for result in (partial, oversized):
        assert result.failure is TransportFailureKind.CONFIDENTIALITY
        assert result.retention_state is RetentionState.SUPPRESSED
        assert result.retained_body is None
        assert result.retained_body_sha256 is None
        assert result.content_length is None
