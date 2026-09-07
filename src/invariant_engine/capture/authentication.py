"""Runtime-only caller-owned Kalshi authentication bindings."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass

from invariant_engine.capture.models import CaptureEnvironment, CaptureTarget
from invariant_engine.capture.specification import expected_origin, signing_path
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import Venue

Signer = Callable[[bytes], str]
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,256}", re.ASCII)
_TIMESTAMP = re.compile(r"[0-9]{1,20}", re.ASCII)
_SIGNER_FAILURE = object()


class AuthenticationBindingError(DomainError):
    """Runtime authentication material is malformed or misbound."""


class SigningError(DomainError):
    """Signing failed without exposing caller-controlled exception material."""


@dataclass(frozen=True, slots=True, repr=False)
class KalshiAuthenticationBinding:
    environment: CaptureEnvironment
    origin: str
    key_id: str
    signer: Signer

    def __repr__(self) -> str:
        return "KalshiAuthenticationBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SignedHeaders:
    timestamp: str
    method: str
    path: str
    headers: tuple[tuple[str, str], ...]

    def __repr__(self) -> str:
        return "SignedHeaders(<redacted>)"


def validate_authentication_bindings(
    targets: tuple[CaptureTarget, ...], bindings: object
) -> dict[CaptureEnvironment, KalshiAuthenticationBinding]:
    if type(bindings) is not tuple:
        raise AuthenticationBindingError("authentication bindings must be an immutable tuple")
    required = {target.environment for target in targets if target.venue is Venue.KALSHI}
    result: dict[CaptureEnvironment, KalshiAuthenticationBinding] = {}
    for binding in bindings:
        if type(binding) is not KalshiAuthenticationBinding:
            raise AuthenticationBindingError("authentication binding must use the exact model type")
        if type(binding.environment) is not CaptureEnvironment or binding.environment not in {
            CaptureEnvironment.DEMO,
            CaptureEnvironment.PRODUCTION,
        }:
            raise AuthenticationBindingError("invalid Kalshi authentication environment")
        if binding.environment in result:
            raise AuthenticationBindingError("duplicate authentication environment")
        if type(binding.origin) is not str or binding.origin != expected_origin(
            Venue.KALSHI, binding.environment
        ):
            raise AuthenticationBindingError("authentication origin is misbound")
        if type(binding.key_id) is not str or _KEY_ID.fullmatch(binding.key_id) is None:
            raise AuthenticationBindingError("invalid authentication key ID")
        if not callable(binding.signer):
            raise AuthenticationBindingError("authentication signer must be callable")
        result[binding.environment] = binding
    if set(result) != required:
        raise AuthenticationBindingError(
            "authentication bindings do not exactly match required environments"
        )
    return result


def _validate_signature(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 4096 or not value.isascii():
        raise SigningError("signer returned an invalid signature")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SigningError("signer returned an invalid signature") from exc
    if not 128 <= len(decoded) <= 1024 or base64.b64encode(decoded).decode("ascii") != value:
        raise SigningError("signer returned an invalid signature")
    return value


def _invoke_signer(signer: Signer, message: bytes) -> object:
    try:
        return signer(message)
    except BaseException:
        return _SIGNER_FAILURE


def sign_target(
    target: CaptureTarget,
    binding: KalshiAuthenticationBinding,
    timestamp: object,
) -> SignedHeaders:
    if target.venue is not Venue.KALSHI:
        raise AuthenticationBindingError("only Kalshi targets may be signed")
    if (
        binding.environment is not target.environment
        or binding.origin != target.origin
        or binding.origin != expected_origin(target.venue, target.environment)
    ):
        raise AuthenticationBindingError("authentication binding does not match target")
    if type(timestamp) is not str or _TIMESTAMP.fullmatch(timestamp) is None:
        raise AuthenticationBindingError("timestamp must be 1 through 20 ASCII digits")
    path = signing_path(target)
    message = (timestamp + "GET" + path).encode("ascii")
    raw_signature = _invoke_signer(binding.signer, message)
    if raw_signature is _SIGNER_FAILURE:
        raise SigningError("caller signer failed")
    signature = _validate_signature(raw_signature)
    return SignedHeaders(
        timestamp=timestamp,
        method="GET",
        path=path,
        headers=(
            ("KALSHI-ACCESS-KEY", binding.key_id),
            ("KALSHI-ACCESS-TIMESTAMP", timestamp),
            ("KALSHI-ACCESS-SIGNATURE", signature),
        ),
    )


__all__ = [
    "AuthenticationBindingError",
    "KalshiAuthenticationBinding",
    "SignedHeaders",
    "Signer",
    "SigningError",
    "sign_target",
    "validate_authentication_bindings",
]
