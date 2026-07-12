"""Authenticated outbound messages for the Nextcloud Talk bot API."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlparse

import httpx


class TalkSendError(RuntimeError):
    """Raised when a response cannot be delivered through Nextcloud Talk."""


class TalkClient:
    """Send messages using the Nextcloud Talk bot-response endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        http_client: httpx.AsyncClient,
        random_factory: Callable[[], str] | None = None,
    ) -> None:
        parsed_url = urlparse(base_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.path not in ("", "/")
            or parsed_url.params
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise TalkSendError("base_url must be a canonical HTTPS origin")
        self._base_url = f"https://{parsed_url.netloc}"
        self._secret = secret
        self._http_client = http_client
        self._random_factory = random_factory or (lambda: secrets.token_urlsafe(48))

    def _signature(self, random_value: str, message: str) -> str:
        return hmac.new(
            self._secret.encode("utf-8"),
            (random_value + message).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def send_message(
        self,
        *,
        room_id: str,
        message: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Send one non-empty message to an authorized Talk conversation."""
        if not (normalized_message := message.strip()):
            raise TalkSendError("refusing to send an empty Talk message")
        if not (normalized_room := room_id.strip()):
            raise TalkSendError("refusing to send to an empty Talk room")

        random_value = self._random_factory()
        if not isinstance(random_value, str) or not random_value:
            raise TalkSendError("random factory returned an invalid value")
        payload: dict[str, Any] = {"message": normalized_message}
        if reply_to is not None:
            payload["replyTo"] = reply_to
        if thread_id is not None:
            payload["threadId"] = thread_id

        try:
            response = await self._http_client.post(
                f"{self._base_url}/ocs/v2.php/apps/spreed/api/v1/bot/"
                f"{quote(normalized_room, safe='')}/message",
                json=payload,
                headers={
                    "Accept": "application/json",
                    "OCS-APIRequest": "true",
                    "X-Nextcloud-Talk-Bot-Random": random_value,
                    "X-Nextcloud-Talk-Bot-Signature": self._signature(
                        random_value, normalized_message
                    ),
                },
            )
        except httpx.HTTPError as error:
            raise TalkSendError("Nextcloud Talk reply transport failure") from error

        if response.status_code != 201:
            raise TalkSendError(
                f"Nextcloud Talk rejected bot reply with HTTP {response.status_code}"
            )
        try:
            meta = response.json()["ocs"]["meta"]
        except (KeyError, TypeError, ValueError) as error:
            raise TalkSendError("Nextcloud Talk returned an invalid OCS response") from error
        if not isinstance(meta, dict) or meta.get("status") != "ok":
            raise TalkSendError("Nextcloud Talk returned an unsuccessful OCS response")
