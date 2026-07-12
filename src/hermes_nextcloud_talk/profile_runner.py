"""Profile-isolated Hermes CLI invocation for the Talk gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class HermesRunError(RuntimeError):
    """Raised when the configured Hermes profile cannot produce a response."""


CommandRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]


async def _run_command(command: list[str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode or 0,
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


class HermesCliRunner:
    """Run one response through a named Hermes profile without reading its data."""

    def __init__(
        self,
        *,
        executable: str = "hermes",
        command_runner: CommandRunner = _run_command,
    ) -> None:
        self._executable = executable
        self._command_runner = command_runner

    async def run(self, *, profile: str, session_key: str, message: str) -> str:
        """Resume/create a named profile-local session and return its final text."""
        command = [
            self._executable,
            "-p",
            profile,
            "--continue",
            session_key,
            "--oneshot",
            message,
        ]
        return_code, stdout, _stderr = await self._command_runner(command)
        if return_code != 0:
            raise HermesRunError(f"Hermes profile invocation failed with exit code {return_code}")
        return stdout.strip()
