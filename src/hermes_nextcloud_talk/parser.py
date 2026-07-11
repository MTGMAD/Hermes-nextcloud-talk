"""Normalization of signed Nextcloud Talk bot events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

MAX_EVENT_BYTES = 256 * 1024
SUPPORTED_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})


class EventParseError(ValueError):
    """Raised when a verified webhook payload is not a supported Talk message."""


@dataclass(frozen=True)
class TalkMessageEvent:
    """The safe, stable fields Hermes needs from one Talk chat message."""

    sender_id: str
    sender_name: str
    room_id: str
    room_name: str
    message_id: str
    message: str
    media_type: str
    thread_id: str | None


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise EventParseError(f"missing or invalid {field}")
    return normalized


def _identifier(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise EventParseError(f"missing or invalid {field}")
    normalized = str(value).strip()
    if not normalized:
        raise EventParseError(f"missing or invalid {field}")
    return normalized


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EventParseError(f"missing or invalid {field}")
    return value


def _decode_json(raw: bytes | str, field: str) -> Any:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise EventParseError(f"invalid {field}") from error


def parse_talk_event(body: bytes) -> TalkMessageEvent:
    """Parse one already-authenticated Nextcloud Talk ``Create`` message event."""
    if len(body) > MAX_EVENT_BYTES:
        raise EventParseError("webhook payload exceeds maximum size")

    payload = _object(_decode_json(body, "JSON webhook payload"), "payload")
    if payload.get("type") != "Create":
        raise EventParseError("unsupported Nextcloud Talk event type")

    actor = _object(payload.get("actor"), "actor")
    note = _object(payload.get("object"), "object")
    target = _object(payload.get("target"), "target")
    if actor.get("type") != "Person":
        raise EventParseError("unsupported actor.type")
    if target.get("type") != "Collection":
        raise EventParseError("unsupported target.type")
    if note.get("type") != "Note" or note.get("name") != "message":
        raise EventParseError("unsupported Nextcloud Talk object")

    raw_content = _required_string(note.get("content"), "object.content")
    content = _object(_decode_json(raw_content, "object.content"), "object.content")
    media_type = _required_string(note.get("mediaType"), "object.mediaType")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise EventParseError("unsupported object.mediaType")

    thread_value = note.get("threadId")
    thread_id = _identifier(thread_value, "object.threadId") if thread_value is not None else None

    return TalkMessageEvent(
        sender_id=_required_string(actor.get("id"), "actor.id"),
        sender_name=_required_string(actor.get("name"), "actor.name"),
        room_id=_required_string(target.get("id"), "target.id"),
        room_name=_required_string(target.get("name"), "target.name"),
        message_id=_identifier(note.get("id"), "object.id"),
        message=_required_string(content.get("message"), "object.content.message"),
        media_type=media_type,
        thread_id=thread_id,
    )
