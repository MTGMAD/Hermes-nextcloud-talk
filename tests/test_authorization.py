from __future__ import annotations

from hermes_nextcloud_talk.authorization import authorize_message
from hermes_nextcloud_talk.config import TalkSettings
from hermes_nextcloud_talk.parser import TalkMessageEvent


def settings(**overrides: object) -> TalkSettings:
    values: dict[str, object] = {
        "base_url": "https://cloud.example.test",
        "bot_secret": "a" * 40,
        "profile": "frank",
        "allowed_users": ["users/alice"],
        "allowed_rooms": ["room-token"],
        "mention_aliases": ["@frank"],
    }
    values.update(overrides)
    return TalkSettings(**values)


def event(
    *,
    sender: str = "users/alice",
    room: str = "room-token",
    message: str = "@Frank hello",
) -> TalkMessageEvent:
    return TalkMessageEvent(
        sender_id=sender,
        sender_name="Alice",
        room_id=room,
        room_name="Engineering",
        message_id="1567",
        message=message,
        media_type="text/markdown",
        thread_id=None,
    )


def test_authorizes_allowlisted_mentioned_group_message() -> None:
    decision = authorize_message(event(), settings())

    assert decision.allowed is True
    assert decision.message == "hello"


def test_rejects_non_allowlisted_sender() -> None:
    decision = authorize_message(event(sender="users/mallory"), settings())

    assert decision.allowed is False
    assert decision.reason == "sender_not_allowed"


def test_rejects_non_allowlisted_room() -> None:
    decision = authorize_message(event(room="other-room"), settings())

    assert decision.allowed is False
    assert decision.reason == "room_not_allowed"


def test_ignores_group_message_without_mention() -> None:
    decision = authorize_message(event(message="hello everyone"), settings())

    assert decision.allowed is False
    assert decision.reason == "mention_required"


def test_rejects_bare_profile_name_without_at_mention() -> None:
    decision = authorize_message(event(message="frank deploy this"), settings())

    assert decision.allowed is False
    assert decision.reason == "mention_required"


def test_can_explicitly_disable_mention_gating() -> None:
    decision = authorize_message(event(message="hello everyone"), settings(require_mention=False))

    assert decision.allowed is True
    assert decision.message == "hello everyone"
