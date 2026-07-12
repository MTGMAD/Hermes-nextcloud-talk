"""Stable Hermes session keys for Nextcloud Talk rooms and threads."""

from __future__ import annotations

from urllib.parse import quote

from hermes_nextcloud_talk.parser import TalkMessageEvent


def _component(value: str) -> str:
    """Encode opaque external identifiers so separators cannot collide."""
    return quote(value, safe="")


def session_key_for_event(event: TalkMessageEvent, *, profile: str) -> str:
    """Return a deterministic profile-scoped key for one Talk room/thread."""
    thread = "thread-root" if event.thread_id is None else f"thread-id-{event.thread_id}"
    return ":".join(
        (
            "nextcloud-talk",
            _component(profile),
            _component(event.room_id),
            _component(thread),
        )
    )
