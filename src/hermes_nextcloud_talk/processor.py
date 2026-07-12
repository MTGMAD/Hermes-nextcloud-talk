"""Framework-independent secure processing pipeline for Talk webhooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hermes_nextcloud_talk.authorization import authorize_message
from hermes_nextcloud_talk.config import TalkSettings
from hermes_nextcloud_talk.idempotency import InMemoryIdempotencyStore
from hermes_nextcloud_talk.parser import parse_talk_event
from hermes_nextcloud_talk.session_router import session_key_for_event
from hermes_nextcloud_talk.signing import verify_inbound_signature
from hermes_nextcloud_talk.talk_client import TalkClient


class HermesRunner(Protocol):
    """Minimal Hermes invocation boundary used by the integration."""

    async def run(self, *, profile: str, session_key: str, message: str) -> str: ...


@dataclass(frozen=True)
class ProcessingResult:
    """Safe outcome for a signed inbound webhook."""

    status: str
    reason: str | None = None


class TalkWebhookProcessor:
    """Compose verification, normalization, policy, Hermes, and Talk delivery."""

    def __init__(
        self,
        *,
        settings: TalkSettings,
        runner: HermesRunner,
        talk_client: TalkClient,
        idempotency_store: InMemoryIdempotencyStore | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._talk_client = talk_client
        self._idempotency_store = idempotency_store or InMemoryIdempotencyStore()

    async def handle(
        self,
        *,
        body: bytes,
        random_header: str | None,
        signature_header: str | None,
    ) -> ProcessingResult:
        """Process one webhook only after authenticating its raw byte payload."""
        verify_inbound_signature(
            secret=self._settings.bot_secret,
            random_header=random_header,
            signature_header=signature_header,
            body=body,
        )
        event = parse_talk_event(body)
        decision = authorize_message(event, self._settings)
        if not decision.allowed:
            return ProcessingResult(status="ignored", reason=decision.reason)

        event_key = f"{event.room_id}:{event.message_id}"
        claim = await self._idempotency_store.claim(event_key)
        if claim.state == "capacity_exhausted":
            return ProcessingResult(status="ignored", reason="idempotency_capacity_exhausted")
        if claim.state == "delivered":
            return ProcessingResult(status="ignored", reason="duplicate_delivered")
        if claim.state == "processing":
            return ProcessingResult(status="ignored", reason="duplicate_in_progress")
        if claim.state == "failed":
            return ProcessingResult(status="ignored", reason="previous_execution_failed")
        if claim.state == "delivering":
            return ProcessingResult(status="ignored", reason="duplicate_delivery_in_progress")
        if claim.token is None:
            raise RuntimeError("idempotency claim did not provide an owner token")

        if claim.state == "response_ready":
            response = claim.response
        else:
            try:
                response = await self._runner.run(
                    profile=self._settings.profile,
                    session_key=session_key_for_event(event, profile=self._settings.profile),
                    message=decision.message or "",
                )
            except BaseException:
                await self._idempotency_store.mark_failed(event_key, claim.token)
                raise
            if not isinstance(response, str) or not response.strip():
                await self._idempotency_store.save_response(event_key, claim.token, "")
                await self._idempotency_store.reserve_delivery(event_key, claim.token)
                await self._idempotency_store.mark_delivered(event_key, claim.token)
                return ProcessingResult(status="ignored", reason="empty_hermes_response")
            await self._idempotency_store.save_response(event_key, claim.token, response)

        if not response:
            return ProcessingResult(status="ignored", reason="empty_hermes_response")
        try:
            delivery_response = await self._idempotency_store.reserve_delivery(
                event_key, claim.token
            )
        except RuntimeError:
            return ProcessingResult(status="ignored", reason="duplicate_delivery_in_progress")
        try:
            await self._talk_client.send_message(
                room_id=event.room_id,
                message=delivery_response,
                reply_to=event.message_id,
                thread_id=event.thread_id,
            )
        except BaseException:
            await self._idempotency_store.release_delivery(event_key, claim.token)
            raise
        await self._idempotency_store.mark_delivered(event_key, claim.token)
        return ProcessingResult(status="replied")
