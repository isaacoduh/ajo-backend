"""TrueLayer request signing helpers."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from truelayer_signing import HttpMethod, sign_with_pem  # type: ignore[import-untyped]


@dataclass(frozen=True)
class SignedTrueLayerRequest:
    body: bytes
    headers: dict[str, str]


def build_signed_json_request(
    *,
    kid: str,
    private_key_pem: str,
    method: HttpMethod,
    path: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    extra_headers: Mapping[str, str] | None = None,
) -> SignedTrueLayerRequest:
    validate_truelayer_signing_path(path)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        **dict(extra_headers or {}),
    }
    tl_signature = (
        sign_with_pem(kid, private_key_pem)
        .set_method(method)
        .set_path(path)
        .add_header("Idempotency-Key", idempotency_key)
        .set_body(body.decode("utf-8"))
        .sign()
    )
    headers["Tl-Signature"] = tl_signature
    return SignedTrueLayerRequest(body=body, headers=headers)


def build_signed_empty_request(
    *,
    kid: str,
    private_key_pem: str,
    method: HttpMethod,
    path: str,
    idempotency_key: str,
    extra_headers: Mapping[str, str] | None = None,
) -> SignedTrueLayerRequest:
    validate_truelayer_signing_path(path)
    headers = {
        "Idempotency-Key": idempotency_key,
        **dict(extra_headers or {}),
    }
    tl_signature = (
        sign_with_pem(kid, private_key_pem)
        .set_method(method)
        .set_path(path)
        .add_header("Idempotency-Key", idempotency_key)
        .set_body("")
        .sign()
    )
    headers["Tl-Signature"] = tl_signature
    return SignedTrueLayerRequest(body=b"", headers=headers)


def validate_truelayer_signing_path(path: str) -> None:
    if "://" in path:
        raise ValueError("TrueLayer signing path must not include scheme or host.")
    if not path.startswith("/"):
        raise ValueError("TrueLayer signing path must start with '/'.")
