from __future__ import annotations

from hermes_nextcloud_talk.parser import TalkMessageEvent
from hermes_nextcloud_talk.session_router import session_key_for_event


def event(*, room: str = "room-token", thread: str | None = None) -> TalkMessageEvent:
    return TalkMessageEvent(
        sender_id="users/alice",
        sender_name="Alice",
        room_id=room,
        room_name="Engineering",
        message_id="1567",
        message="hello",
        media_type="text/markdown",
        thread_id=thread,
    )


def test_uses_distinct_room_and_thread_session_key() -> None:
    assert session_key_for_event(event(thread="42"), profile="frank") == (
        "nextcloud-talk:frank:room-token:thread-id-42"
    )


def test_uses_root_when_talk_thread_is_absent() -> None:
    assert session_key_for_event(event(), profile="frank") == (
        "nextcloud-talk:frank:room-token:thread-root"
    )


def test_no_thread_does_not_collide_with_real_root_thread_id() -> None:
    assert session_key_for_event(event(), profile="frank") != session_key_for_event(
        event(thread="root"), profile="frank"
    )


def test_uses_different_keys_for_different_rooms() -> None:
    assert session_key_for_event(event(room="room-a"), profile="frank") != session_key_for_event(
        event(room="room-b"), profile="frank"
    )
