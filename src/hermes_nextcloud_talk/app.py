"""Minimal ASGI adapter for authenticated Nextcloud Talk webhook delivery."""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status

from hermes_nextcloud_talk.processor import ProcessingResult
from hermes_nextcloud_talk.signing import SignatureError


class WebhookProcessor(Protocol):
    """Interface exposed by the framework-independent Talk processor."""

    async def handle(
        self,
        *,
        body: bytes,
        random_header: str | None,
        signature_header: str | None,
    ) -> ProcessingResult: ...


def create_app(processor: WebhookProcessor) -> FastAPI:
    """Create an ASGI app that passes exact inbound bytes to the processor."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
    async def webhook(request: Request) -> dict[str, str | None]:
        try:
            result = await processor.handle(
                body=await request.body(),
                random_header=request.headers.get("X-Nextcloud-Talk-Random"),
                signature_header=request.headers.get("X-Nextcloud-Talk-Signature"),
            )
        except SignatureError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized webhook",
            ) from error
        return {"status": result.status, "reason": result.reason}

    return app
