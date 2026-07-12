from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from hermes_nextcloud_talk.app import create_app
from hermes_nextcloud_talk.processor import ProcessingResult
from hermes_nextcloud_talk.signing import SignatureError


@dataclass
class FakeProcessor:
    result: ProcessingResult = ProcessingResult(status="replied")
    error: Exception | None = None
    seen: dict[str, object] | None = None

    async def handle(
        self,
        *,
        body: bytes,
        random_header: str | None,
        signature_header: str | None,
    ) -> ProcessingResult:
        self.seen = {
            "body": body,
            "random_header": random_header,
            "signature_header": signature_header,
        }
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_health_endpoint_reports_ready() -> None:
    app = create_app(FakeProcessor())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_forwards_exact_body_and_talk_headers() -> None:
    processor = FakeProcessor(result=ProcessingResult(status="ignored", reason="mention_required"))
    app = create_app(processor)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook",
            content=b'{"raw": true}',
            headers={
                "X-Nextcloud-Talk-Random": "random",
                "X-Nextcloud-Talk-Signature": "signature",
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "ignored", "reason": "mention_required"}
    assert processor.seen == {
        "body": b'{"raw": true}',
        "random_header": "random",
        "signature_header": "signature",
    }


@pytest.mark.asyncio
async def test_rejects_invalid_signatures_without_exposing_details() -> None:
    app = create_app(FakeProcessor(error=SignatureError("invalid Nextcloud Talk signature")))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/webhook", content=b"{}")

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized webhook"}
