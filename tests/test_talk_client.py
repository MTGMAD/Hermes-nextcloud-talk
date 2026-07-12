from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from hermes_nextcloud_talk.talk_client import (
    TalkClient,
    TalkSendError,
)

SECRET = "s" * 40
RANDOM = "r" * 64


def expected_signature(message: str) -> str:
    return hmac.new(
        SECRET.encode(),
        (RANDOM + message).encode(),
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.asyncio
async def test_sends_signed_reply_to_talk_bot_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"ocs": {"meta": {"status": "ok"}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = TalkClient(
            base_url="https://cloud.example.test",
            secret=SECRET,
            http_client=http_client,
            random_factory=lambda: RANDOM,
        )
        await client.send_message(
            room_id="room-token",
            message="Hermes response",
            reply_to="1567",
            thread_id="42",
        )

    assert seen["url"] == (
        "https://cloud.example.test/ocs/v2.php/apps/spreed/api/v1/bot/room-token/message"
    )
    assert seen["headers"]["x-nextcloud-talk-bot-random"] == RANDOM
    assert seen["headers"]["x-nextcloud-talk-bot-signature"] == expected_signature(
        "Hermes response"
    )
    assert seen["headers"]["ocs-apirequest"] == "true"
    assert seen["body"] == {
        "message": "Hermes response",
        "replyTo": "1567",
        "threadId": "42",
    }


@pytest.mark.asyncio
async def test_raises_without_sending_empty_message() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(201))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TalkClient(
            base_url="https://cloud.example.test",
            secret=SECRET,
            http_client=http_client,
            random_factory=lambda: RANDOM,
        )
        with pytest.raises(TalkSendError, match="empty"):
            await client.send_message(room_id="room-token", message="   ")


@pytest.mark.asyncio
async def test_raises_descriptive_error_for_talk_rejection() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TalkClient(
            base_url="https://cloud.example.test",
            secret=SECRET,
            http_client=http_client,
            random_factory=lambda: RANDOM,
        )
        with pytest.raises(TalkSendError, match="401"):
            await client.send_message(room_id="room-token", message="Hermes response")


@pytest.mark.asyncio
async def test_rejects_non_https_client_endpoint() -> None:
    async with httpx.AsyncClient() as http_client:
        with pytest.raises(TalkSendError, match="canonical HTTPS origin"):
            TalkClient(
                base_url="http://cloud.example.test",
                secret=SECRET,
                http_client=http_client,
            )


@pytest.mark.asyncio
async def test_rejects_success_status_with_invalid_ocs_envelope() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(201, json={"ocs": {}}))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TalkClient(
            base_url="https://cloud.example.test",
            secret=SECRET,
            http_client=http_client,
            random_factory=lambda: RANDOM,
        )
        with pytest.raises(TalkSendError, match="OCS"):
            await client.send_message(room_id="room-token", message="Hermes response")


@pytest.mark.asyncio
async def test_wraps_transport_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = TalkClient(
            base_url="https://cloud.example.test",
            secret=SECRET,
            http_client=http_client,
            random_factory=lambda: RANDOM,
        )
        with pytest.raises(TalkSendError, match="transport"):
            await client.send_message(room_id="room-token", message="Hermes response")
