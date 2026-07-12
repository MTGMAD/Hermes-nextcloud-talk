"""Runtime configuration loading for the standalone Talk webhook service."""

from __future__ import annotations

import os

from hermes_nextcloud_talk.config import TalkSettings


class RuntimeConfigError(ValueError):
    """Raised when required non-committed service configuration is absent."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeConfigError(f"missing required environment variable: {name}")
    return value


def _csv(name: str) -> list[str]:
    return [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]


def settings_from_environment() -> TalkSettings:
    """Load one profile-isolated Talk bot configuration from local environment."""
    allow_all_users = os.environ.get("NEXTCLOUD_TALK_ALLOW_ALL_USERS", "").lower() == "true"
    development_mode = os.environ.get("NEXTCLOUD_TALK_DEVELOPMENT_MODE", "").lower() == "true"
    require_mention = os.environ.get("NEXTCLOUD_TALK_REQUIRE_MENTION", "true").lower() != "false"
    return TalkSettings(
        base_url=_required("NEXTCLOUD_TALK_BASE_URL"),
        bot_secret=_required("NEXTCLOUD_TALK_BOT_SECRET"),
        profile=_required("HERMES_PROFILE"),
        allowed_users=_csv("NEXTCLOUD_TALK_ALLOWED_USERS"),
        allowed_rooms=_csv("NEXTCLOUD_TALK_ALLOWED_ROOMS"),
        allow_all_users=allow_all_users,
        development_mode=development_mode,
        require_mention=require_mention,
        mention_aliases=_csv("NEXTCLOUD_TALK_MENTION_ALIASES"),
    )
