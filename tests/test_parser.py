from __future__ import annotations

import json

import pytest

from hermes_nextcloud_talk.parser import EventParseError, parse_talk_event


def message_event(*, actor_id: str = "users/alice", thread_id: int | None = None) -> bytes:
    note: dict[str, object] = {
        "type": "Note",
        "id": "1567",
        "name": "message",
        "content": json.dumps({"message": "@Frank hello Talk", "parameters": {}}),
        "mediaType": "text/markdown",
    }
    if thread_id is not None:
        note["threadId"] = thread_id
    return json.dumps(
        {
            "type": "Create",
            "actor": {"type": "Person", "id": actor_id, "name": "Alice"},
            "object": note,
            "target": {"type": "Collection", "id": "room-token", "name": "Engineering"},
        }
    ).encode("utf-8")


def test_parses_talk_message_into_stable_identifiers() -> None:
    event = parse_talk_event(message_event(thread_id=42))

    assert event.sender_id == "users/alice"
    assert event.sender_name == "Alice"
    assert event.room_id == "room-token"
    assert event.room_name == "Engineering"
    assert event.message_id == "1567"
    assert event.thread_id == "42"
    assert event.message == "@Frank hello Talk"
    assert event.media_type == "text/markdown"


def test_rejects_non_message_events() -> None:
    payload = json.dumps({"type": "Join", "actor": {}, "object": {}, "target": {}}).encode()

    with pytest.raises(EventParseError, match="unsupported"):
        parse_talk_event(payload)


def test_rejects_malformed_nested_message_content() -> None:
    payload = json.loads(message_event())
    payload["object"]["content"] = "not-json"

    with pytest.raises(EventParseError, match="content"):
        parse_talk_event(json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (("actor", "type"), "Application", "actor.type"),
        (("target", "type"), "Person", "target.type"),
        (("object", "mediaType"), "application/octet-stream", "mediaType"),
        (("actor", "id"), "   ", "actor.id"),
        (("object", "id"), True, "object.id"),
        (("object", "threadId"), False, "object.threadId"),
    ],
)
def test_rejects_unsafe_or_malformed_message_metadata(
    path: tuple[str, str], value: object, error: str
) -> None:
    payload = json.loads(message_event())
    payload[path[0]][path[1]] = value

    with pytest.raises(EventParseError, match=error):
        parse_talk_event(json.dumps(payload).encode())
