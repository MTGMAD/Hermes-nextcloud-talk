from __future__ import annotations

import pytest

from hermes_nextcloud_talk.profile_runner import HermesCliRunner, HermesRunError


@pytest.mark.asyncio
async def test_invokes_requested_profile_with_isolated_session_key() -> None:
    seen: list[str] = []

    async def command_runner(command: list[str]) -> tuple[int, str, str]:
        seen.extend(command)
        return 0, "Hermes answer\n", ""

    runner = HermesCliRunner(command_runner=command_runner)
    response = await runner.run(
        profile="frank",
        session_key="nextcloud-talk:frank:room-token:thread-id-42",
        message="hello",
    )

    assert response == "Hermes answer"
    assert seen == [
        "hermes",
        "-p",
        "frank",
        "--continue",
        "nextcloud-talk:frank:room-token:thread-id-42",
        "--oneshot",
        "hello",
    ]


@pytest.mark.asyncio
async def test_does_not_expose_runner_stderr_in_error() -> None:
    async def command_runner(_: list[str]) -> tuple[int, str, str]:
        return 1, "", "secret-looking failure diagnostic"

    runner = HermesCliRunner(command_runner=command_runner)

    with pytest.raises(HermesRunError, match="exit code 1") as error:
        await runner.run(profile="frank", session_key="session", message="hello")

    assert "secret-looking" not in str(error.value)
