# Hermes Nextcloud Talk

> **Pre-alpha:** A secure webhook gateway that connects [Nextcloud Talk](https://nextcloud.com/talk/) bots to isolated [Hermes Agent](https://github.com/NousResearch/hermes-agent) profiles.

Hermes Nextcloud Talk receives a signed Talk bot webhook, validates it before parsing, applies room/user and `@mention` policy, runs exactly one configured Hermes profile in a room/thread-scoped session, and posts the response to the originating Talk conversation.

## Current status

The local service and core message flow are implemented and tested:

- signed inbound HMAC validation over exact raw webhook bytes;
- safe Talk ActivityStreams message parsing;
- HTTPS-only endpoint configuration and explicit room/user allowlists;
- `@`-mention gating for group messages by default;
- replay/idempotency protection for a single service process;
- separate Hermes sessions per profile, Talk room, and Talk thread;
- profile-safe execution through `hermes -p <profile>`;
- signed outbound Talk bot replies with OCS response validation;
- loopback-bound ASGI webhook service with `/healthz` and `/webhook` endpoints.

It is **not production-ready yet**. In particular, the current idempotency store is process-local, so production multi-worker deployment needs a shared durable store. A live bot smoke test against a non-production Talk room is also still required before release.

## Server compatibility

The development target at `https://nc.lowfog.net` was checked through public read-only endpoints:

```text
Nextcloud 33.0.2
Talk 23.0.6
bots-v1: supported
threads: supported
```

This supports the intended bot response and thread/session-routing model.

## Local development

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

## Run the webhook service locally

1. Copy `.env.example` to a local, ignored `.env` file and fill in the values. Do not commit it.
2. Export those values in your shell using your preferred secret-management approach.
3. Start the service:

   ```bash
   .venv/bin/hermes-nextcloud-talk
   ```

It listens on `127.0.0.1:8790` by default. Verify it locally:

```bash
curl http://127.0.0.1:8790/healthz
# {"status":"ok"}
```

Expose it only through an HTTPS reverse proxy when ready for a real Talk bot. Do not bind the service directly to the public internet.

## Nextcloud Talk requirements

- Python 3.10+
- Hermes Agent and an existing Hermes profile
- Nextcloud Talk with `bots-v1`
- Nextcloud administrator access to install a bot and enable it in a non-production conversation
- A stable HTTPS callback URL reachable by the Nextcloud server

## Security notes

Never commit Talk bot secrets, app passwords, room tokens, production webhook fixtures, or `.env` files. Use a distinct bot secret per integration instance. The service validates inbound request signatures before parsing data and does not log those secrets.

## License

[MIT](LICENSE)
