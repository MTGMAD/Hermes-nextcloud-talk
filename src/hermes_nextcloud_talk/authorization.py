"""Authorization and mention gating for Nextcloud Talk messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hermes_nextcloud_talk.config import TalkSettings
from hermes_nextcloud_talk.parser import TalkMessageEvent


@dataclass(frozen=True)
class AuthorizationDecision:
    """Whether an event can invoke Hermes and the user content to forward."""

    allowed: bool
    reason: str | None = None
    message: str | None = None


def _deny(reason: str) -> AuthorizationDecision:
    return AuthorizationDecision(allowed=False, reason=reason)


def authorize_message(event: TalkMessageEvent, settings: TalkSettings) -> AuthorizationDecision:
    """Apply allowlists and optional group mention gating to one Talk message."""
    if not settings.allow_all_users:
        if settings.allowed_users and event.sender_id not in settings.allowed_users:
            return _deny("sender_not_allowed")
        if settings.allowed_rooms and event.room_id not in settings.allowed_rooms:
            return _deny("room_not_allowed")

    if not settings.require_mention:
        return AuthorizationDecision(allowed=True, message=event.message)

    for alias in settings.mention_aliases:
        match = re.search(rf"(?i)(?<![\w@]){re.escape(alias)}\b", event.message)
        if match is None:
            continue
        content = (event.message[: match.start()] + event.message[match.end() :]).strip(" \t,:-")
        if content:
            return AuthorizationDecision(allowed=True, message=content)
        return _deny("empty_message_after_mention")
    return _deny("mention_required")
