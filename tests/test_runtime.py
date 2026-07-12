from __future__ import annotations

import os

import pytest

from hermes_nextcloud_talk.runtime import RuntimeConfigError, settings_from_environment


def environment() -> dict[str, str]:
    return {
        "NEXTCLOUD_TALK_BASE_URL": "https://cloud.example.test",
        "NEXTCLOUD_TALK_BOT_SECRET": "s" * 40,
        "HERMES_PROFILE": "frank",
        "NEXTCLOUD_TALK_ALLOWED_USERS": "users/alice, users/bob",
        "NEXTCLOUD_TALK_ALLOWED_ROOMS": "room-a,room-b",
    }


def test_loads_safe_runtime_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXTCLOUD_TALK_ALLOW_ALL_USERS", raising=False)
    for key, value in environment().items():
        monkeypatch.setenv(key, value)

    settings = settings_from_environment()

    assert settings.base_url == "https://cloud.example.test"
    assert settings.profile == "frank"
    assert settings.allowed_users == ["users/alice", "users/bob"]
    assert settings.allowed_rooms == ["room-a", "room-b"]


def test_rejects_missing_required_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("NEXTCLOUD_TALK_BOT_SECRET")

    with pytest.raises(RuntimeConfigError, match="NEXTCLOUD_TALK_BOT_SECRET"):
        settings_from_environment()


def test_does_not_mutate_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in environment().items():
        monkeypatch.setenv(key, value)

    before = dict(os.environ)
    settings_from_environment()

    assert dict(os.environ) == before
