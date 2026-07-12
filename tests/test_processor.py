from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field

import pytest

from hermes_nextcloud_talk.config import TalkSettings
from hermes_nextcloud_talk.idempotency import InMemoryIdempotencyStore
from hermes_nextcloud_talk.processor import TalkWebhookProcessor

SECRET = "s" * 40
RANDOM = "r" * 64


@dataclass
class FakeRunner:
    responses: list[str] = field(default_factory=lambda: ["Hermes response"])
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def run(self, *, profile: str, session_key: str, message: str) -> str:
        self.calls.append((profile, session_key, message))
        return self.responses.pop(0)


@dataclass
class FakeTalkClient:
    calls: list[dict[str, str | None]] = field(default_factory=list)

    async def send_message(
        self,
        *,
        room_id: str,
        message: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "room_id": room_id,
                "message": message,
                "reply_to": reply_to,
                "thread_id": thread_id,
            }
        )


def settings() -> TalkSettings:
    return TalkSettings(
        base_url="https://cloud.example.test",
        bot_secret=SECRET,
        profile="frank",
        allowed_users=["users/alice"],
        allowed_rooms=["room-token"],
    )


def payload(*, message: str = "@frank hello", actor: str = "users/alice") -> bytes:
    return json.dumps(
        {
            "type": "Create",
            "actor": {"type": "Person", "id": actor, "name": "Alice"},
            "target": {"type": "Collection", "id": "room-token", "name": "Engineering"},
            "object": {
                "type": "Note",
                "name": "message",
                "id": "1567",
                "mediaType": "text/markdown",
                "content": json.dumps({"message": message}),
                "threadId": "42",
            },
        }
    ).encode()


def signature(body: bytes) -> str:
    return hmac.new(SECRET.encode(), RANDOM.encode() + body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_verifies_processes_routes_and_replies() -> None:
    runner = FakeRunner()
    talk_client = FakeTalkClient()
    processor = TalkWebhookProcessor(settings=settings(), runner=runner, talk_client=talk_client)
    body = payload()

    result = await processor.handle(
        body=body,
        random_header=RANDOM,
        signature_header=signature(body),
    )

    assert result.status == "replied"
    assert runner.calls == [("frank", "nextcloud-talk:frank:room-token:thread-id-42", "hello")]
    assert talk_client.calls == [
        {
            "room_id": "room-token",
            "message": "Hermes response",
            "reply_to": "1567",
            "thread_id": "42",
        }
    ]


@pytest.mark.asyncio
async def test_ignores_authorized_message_without_a_mention() -> None:
    runner = FakeRunner()
    talk_client = FakeTalkClient()
    processor = TalkWebhookProcessor(settings=settings(), runner=runner, talk_client=talk_client)
    body = payload(message="hello everyone")

    result = await processor.handle(
        body=body,
        random_header=RANDOM,
        signature_header=signature(body),
    )

    assert result.status == "ignored"
    assert result.reason == "mention_required"
    assert runner.calls == []
    assert talk_client.calls == []


@pytest.mark.asyncio
async def test_deduplicates_delivered_event_before_runner_execution() -> None:
    runner = FakeRunner()
    talk_client = FakeTalkClient()
    processor = TalkWebhookProcessor(
        settings=settings(),
        runner=runner,
        talk_client=talk_client,
        idempotency_store=InMemoryIdempotencyStore(),
    )
    body = payload()

    await processor.handle(body=body, random_header=RANDOM, signature_header=signature(body))
    result = await processor.handle(
        body=body,
        random_header=RANDOM,
        signature_header=signature(body),
    )

    assert result.status == "ignored"
    assert result.reason == "duplicate_delivered"
    assert len(runner.calls) == 1
    assert len(talk_client.calls) == 1
