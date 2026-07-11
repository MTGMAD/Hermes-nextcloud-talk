from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_nextcloud_talk.config import TalkSettings


def valid_settings(**overrides: object) -> TalkSettings:
    values: dict[str, object] = {
        "base_url": "https://cloud.example.test",
        "bot_secret": "a" * 40,
        "profile": "frank",
        "allowed_users": ["users/alice"],
        "allowed_rooms": ["room-token"],
    }
    values.update(overrides)
    return TalkSettings(**values)


def test_requires_at_least_one_allowlist_in_production() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        valid_settings(allowed_users=[], allowed_rooms=[])


def test_group_messages_require_mentions_by_default() -> None:
    settings = valid_settings()

    assert settings.require_mention is True


def test_rejects_non_https_base_url() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        valid_settings(base_url="http://cloud.example.test")


def test_allows_explicit_development_open_access() -> None:
    settings = valid_settings(
        allowed_users=[],
        allowed_rooms=[],
        allow_all_users=True,
        development_mode=True,
    )

    assert settings.allow_all_users is True


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:password@cloud.example.test",
        "https://cloud.example.test/path",
        "https://cloud.example.test/?query=value",
        "https://cloud.example.test/#fragment",
    ],
)
def test_rejects_non_origin_base_urls(base_url: str) -> None:
    with pytest.raises(ValidationError, match="origin"):
        valid_settings(base_url=base_url)


def test_normalizes_allowlists_and_rejects_whitespace_profile() -> None:
    settings = valid_settings(allowed_users=[" users/alice "], allowed_rooms=[" room-token "])

    assert settings.allowed_users == ["users/alice"]
    assert settings.allowed_rooms == ["room-token"]

    with pytest.raises(ValidationError, match="profile"):
        valid_settings(profile="   ")


def test_rejects_open_access_without_explicit_development_mode() -> None:
    with pytest.raises(ValidationError, match="development_mode"):
        valid_settings(allow_all_users=True)
