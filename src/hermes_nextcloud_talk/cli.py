"""Service composition and command-line entry point for Nextcloud Talk."""

from __future__ import annotations

import os

import httpx
import uvicorn

from hermes_nextcloud_talk.app import create_app
from hermes_nextcloud_talk.processor import TalkWebhookProcessor
from hermes_nextcloud_talk.profile_runner import HermesCliRunner
from hermes_nextcloud_talk.runtime import RuntimeConfigError, settings_from_environment
from hermes_nextcloud_talk.talk_client import TalkClient


def build_app():
    """Construct a live webhook app from local, non-committed environment settings."""
    settings = settings_from_environment()
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    talk_client = TalkClient(
        base_url=settings.base_url,
        secret=settings.bot_secret,
        http_client=http_client,
    )
    processor = TalkWebhookProcessor(
        settings=settings,
        runner=HermesCliRunner(),
        talk_client=talk_client,
    )
    return create_app(processor)


def main() -> None:
    """Run the webhook service on loopback unless explicitly overridden."""
    host = os.environ.get("NEXTCLOUD_TALK_LISTEN_HOST", "127.0.0.1")
    port = int(os.environ.get("NEXTCLOUD_TALK_LISTEN_PORT", "8790"))
    try:
        app = build_app()
    except RuntimeConfigError as error:
        raise SystemExit(f"configuration error: {error}") from error
    uvicorn.run(app, host=host, port=port, log_level="info")
