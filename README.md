# Hermes Nextcloud Talk

> **Pre-alpha:** This repository is building a profile-aware [Hermes Agent](https://github.com/NousResearch/hermes-agent) gateway plugin for [Nextcloud Talk](https://nextcloud.com/talk/).

The intended plugin will validate signed Nextcloud Talk bot webhooks, route an authorized message to an isolated Hermes profile, and return the response to the originating Talk conversation. Only the initial HMAC verifier exists today; no webhook listener, replay protection, authorization policy, Hermes dispatch, or outbound Talk client has been released yet.

## Planned capabilities

- Secure HMAC-SHA256 validation for Nextcloud Talk bot webhooks.
- One Nextcloud Talk bot per isolated Hermes profile.
- Multiple Hermes bots/profiles in the same Nextcloud Talk group.
- Room and user allowlists, with mention gating enabled by default in groups.
- Stable session routing per Talk room; capability-gated routing per Talk thread where supported.
- A future optional router mode for a single Talk bot to dispatch explicit mentions to several Hermes profiles.

## Status

The project is in initial implementation. The current security foundation verifies Nextcloud Talk webhook signatures. It is **not ready for production or installation yet**.

## Requirements (planned)

- Python 3.10+
- Hermes Agent
- A Nextcloud Talk instance with the `bots-v1` capability (initially documented from Nextcloud 27.1 / Talk 17.1)
- Nextcloud administrator access to install and enable a Talk bot per conversation
- A stable HTTPS endpoint reachable by the Nextcloud server

## Development

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

## Security

Do not commit Talk bot secrets, app passwords, room tokens, production request fixtures, or `.env` files. See the implementation plan under `.hermes/plans/` for the project security model and staged delivery plan.

## License

[MIT](LICENSE)
