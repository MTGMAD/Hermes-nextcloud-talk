"""Nextcloud Talk webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac


class SignatureError(ValueError):
    """Raised when an inbound Nextcloud Talk webhook cannot be authenticated."""


def verify_inbound_signature(
    *,
    secret: str,
    random_header: str | None,
    signature_header: str | None,
    body: bytes,
) -> None:
    """Validate the Talk HMAC over the random header concatenated with raw body."""
    if not secret or not random_header or not signature_header:
        raise SignatureError("missing Nextcloud Talk signature data")

    try:
        provided = bytes.fromhex(signature_header)
    except ValueError as error:
        raise SignatureError("malformed Nextcloud Talk signature") from error

    expected = hmac.new(
        secret.encode("utf-8"),
        random_header.encode("utf-8") + body,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, provided):
        raise SignatureError("invalid Nextcloud Talk signature")
