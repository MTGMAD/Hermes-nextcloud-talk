# Hermes Nextcloud Talk Gateway Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build and publish `MTGMAD/Hermes-nextcloud-talk` as a secure, installable Hermes Agent gateway plugin that connects Nextcloud Talk bot webhooks to Hermes profiles, supports group rooms and mention gating, and is designed to add native Talk-thread-to-Hermes-session routing.

**Architecture:** Ship a standalone Python plugin package rather than modifying the Hermes core. The plugin receives signed Nextcloud Talk bot webhooks over HTTPS, normalizes them to Hermes gateway messages, dispatches them to a selected isolated Hermes profile, and posts the generated reply back through Talk’s bot endpoint. Start with one profile per bot instance; add an optional router mode later for one Talk bot to dispatch mentions to many Hermes profiles.

**Tech Stack:** Python 3.10+, `httpx`, `pydantic`, `pytest`, `pytest-asyncio`, `ruff`, `mypy` (optional initially), GitHub Actions; Hermes Agent platform-plugin API; Nextcloud Talk Bots API (`bots-v1`); HMAC-SHA256.

---

## 1. Scope and non-negotiable behavior

### v0.1 acceptance criteria

- A Nextcloud Talk administrator can install a webhook bot with `occ talk:bot:install` and point it at a public HTTPS endpoint operated by the plugin.
- The plugin rejects unsigned, malformed, replayed, or unauthorized inbound requests before they reach Hermes.
- A valid Talk message in an authorized room routes to exactly one configured Hermes profile.
- The response is sent to the same Talk conversation through `POST /ocs/v2.php/apps/spreed/api/v1/bot/{token}/message`.
- Group rooms require a mention by default; direct/explicitly configured rooms may opt out.
- Distinct Talk rooms maintain distinct Hermes sessions.
- If the server advertises Talk’s `threads` capability, distinct Talk threads within the same room maintain distinct Hermes sessions.
- The plugin never reads another Hermes profile’s config, memory, auth, or secrets directly. It invokes that profile through a profile-safe Hermes boundary.
- Repository is public, MIT licensed, linted, tested, documented, and releasable.

### Explicitly defer from v0.1

- One bot dynamically routing to multiple profiles (router mode).
- Attachments, voice/media uploads, reactions, and command menus.
- Automatic remote deployment/tunnel provisioning.
- A Hermes core patch or bundled Hermes-plugin change.
- A PyPI release before a live end-to-end smoke test succeeds.

---

## 2. Facts confirmed before implementation

1. Repository exists and is public: `https://github.com/MTGMAD/Hermes-nextcloud-talk`.
2. Local clone is `/Users/aiuser/Hermes/dev/Hermes-nextcloud-talk`, branch `main`, only `README.md` and MIT `LICENSE` currently exist.
3. No existing Hermes Nextcloud Talk adapter was found in the installed Hermes source or repository searches.
4. Nextcloud Talk webhook bots require the `bots-v1` capability, documented as available from Nextcloud 27.1 / Talk 17.1.
5. Inbound Talk bot requests are HMAC-SHA256 signed over `X-Nextcloud-Talk-Random + raw request body` using the bot secret.
6. Talk message events contain sender (`actor`), conversation token (`target.id`), message ID (`object.id`), and a JSON-encoded chat body (`object.content`).
7. Talk bot replies use the bot endpoint above and support `replyTo`; Talk’s Chat API documents `threadId` and `threadTitle` subject to the server’s `threads` capability.

**Important uncertainty to resolve in the first live API spike:** The exact event shape and outbound thread parameters exposed to *bot* requests must be verified against a real supported Nextcloud Talk server. Do not claim full Telegram-topic parity until this is proven end to end.

---

## 3. Target repository layout

```text
Hermes-nextcloud-talk/
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
├── pyproject.toml
├── plugin.yaml
├── .gitignore
├── .env.example
├── .github/
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   └── feature_request.yml
│   └── workflows/
│       └── ci.yml
├── docs/
│   ├── architecture.md
│   ├── nextcloud-admin-setup.md
│   ├── hermes-installation.md
│   ├── configuration.md
│   ├── security.md
│   ├── threads-and-topics.md
│   ├── multi-profile-roadmap.md
│   └── troubleshooting.md
├── examples/
│   ├── config.single-profile.yaml
│   ├── config.multi-bot.yaml
│   ├── reverse-proxy.nginx.conf
│   └── occ-install-example.sh
├── src/hermes_nextcloud_talk/
│   ├── __init__.py
│   ├── plugin.py
│   ├── adapter.py
│   ├── config.py
│   ├── cli.py
│   ├── app.py
│   ├── models.py
│   ├── signing.py
│   ├── replay.py
│   ├── parser.py
│   ├── talk_client.py
│   ├── session_router.py
│   ├── profile_runner.py
│   ├── mentions.py
│   ├── capability_client.py
│   └── logging.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── inbound_message.json
    │   ├── inbound_reply.json
    │   ├── inbound_bot_added.json
    │   └── capabilities_threads.json
    ├── test_config.py
    ├── test_signing.py
    ├── test_replay.py
    ├── test_parser.py
    ├── test_mentions.py
    ├── test_talk_client.py
    ├── test_session_router.py
    ├── test_profile_runner.py
    ├── test_webhook_app.py
    └── test_plugin_contract.py
```

---

## 4. Configuration model

### v0.1: one Hermes profile per plugin instance/bot

All credentials belong in a local `.env` or Hermes profile `.env`; no credentials are committed.

```env
# Required secrets
NEXTCLOUD_TALK_BASE_URL=https://cloud.example.example
NEXTCLOUD_TALK_BOT_SECRET=replace-with-random-shared-secret
NEXTCLOUD_TALK_WEBHOOK_TOKEN=replace-with-external-path-token

# Runtime selection
HERMES_PROFILE=frank
NEXTCLOUD_TALK_LISTEN_HOST=127.0.0.1
NEXTCLOUD_TALK_LISTEN_PORT=8790
```

Non-secret behavior belongs in `config.yaml`:

```yaml
nextcloud_talk:
  enabled: true
  profile: frank
  display_name: Frank
  webhook_path: /nextcloud-talk/webhook
  require_mention: true
  mention_patterns:
    - '(?<![\\w@])@?frank\\b[,:\\-]?'
  allowed_users:
    - users/alice
  allowed_rooms:
    - room-token-1
  allow_direct_messages: true
  replay_window_seconds: 300
  max_message_chars: 32000
  session_scope: room_thread
```

### Routing key

The canonical session key must be deterministic and profile-scoped:

```text
nextcloud-talk:{profile}:{conversation_token}:{thread_id_or_root}
```

- `conversation_token` comes from `target.id`.
- `thread_id_or_root` is `root` when no thread is present.
- Never derive a session key from display names.
- Do not place raw bot secrets or request body content in session keys/logs.

### Future router mode

Do not implement in v0.1, but reserve a schema extension:

```yaml
nextcloud_talk:
  router:
    enabled: false
    routes:
      - profile: frank
        mention_patterns: ['(?<![\\w@])@?frank\\b']
      - profile: researcher
        mention_patterns: ['(?<![\\w@])@?research(er)?\\b']
```

Router mode runs an independent dispatcher process and invokes `hermes -p <profile>` or an approved Hermes API boundary. It must never import profile internals or share profile secrets.

---

## 5. Implementation tasks

### Task 1: Establish project metadata and contributor baseline

**Objective:** Turn the empty repository into a conventional Python OSS project without implementing transport logic.

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `CHANGELOG.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Modify: `README.md`

**Steps:**
1. Choose Python `>=3.10`; use a `src/` package layout.
2. Define initial dependencies: `httpx`, `pydantic`, and an ASGI framework only after confirming how Hermes platform plugins host inbound HTTP. Prefer Hermes’s native gateway/plugin lifecycle if it exposes a supported listener hook; otherwise use a small ASGI app with `uvicorn` extra.
3. Define development dependencies: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`.
4. Add `ruff check`, `ruff format --check`, and `pytest` scripts/commands.
5. Rewrite README with truthful current status: “pre-alpha / design and API-validation phase,” not “ready to install.”
6. Add contributor and security reporting guidance.

**Verification:**
```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

**Commit:**
```bash
git add pyproject.toml .gitignore .env.example README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md
git commit -m "chore: scaffold Python plugin project"
```

---

### Task 2: Perform a live Nextcloud Talk API compatibility spike

**Objective:** Prove exact server requirements and capture sanitized fixtures from a real Nextcloud Talk server before adapter implementation.

**Files:**
- Create: `docs/nextcloud-admin-setup.md`
- Create: `docs/api-compatibility-matrix.md`
- Create: `examples/occ-install-example.sh`
- Create: `tests/fixtures/` sanitized payloads

**Steps:**
1. Record Nextcloud server version, Talk app version, and returned Talk capabilities. Require `bots-v1`; record whether `threads`, `chat-replies`, `chat-reference-id`, and `silent-send` are present.
2. Have the Nextcloud administrator run `occ talk:bot:install --help` and create a dedicated test bot. Store secrets only in local secure configuration.
3. Create a test room, add the bot, and capture a signed inbound message request. Remove user names, public hostnames, room tokens, message text, signatures, and secrets before committing a fixture.
4. Verify the HMAC algorithm against the real event: `HMAC_SHA256(random_header + raw_body, bot_secret)`.
5. Send a bot reply to the same room using the documented endpoint and capture only sanitized request/response shapes.
6. Test reply-to behavior (`replyTo`).
7. If the `threads` capability is present: create a thread from the official client, capture inbound behavior, and verify whether bot outbound messages accept `threadId`/`threadTitle`. If unsupported or unclear, document it as a v0.1 limitation rather than guessing.
8. Document reverse-proxy/public-HTTPS requirements. Nextcloud must be able to reach the webhook endpoint.

**Verification:**
- A signed inbound event validates locally.
- A bot reply is visible in the intended Talk test room.
- Capability matrix identifies the precise minimum supported version for this project.

**Commit:**
```bash
git add docs/ examples/ tests/fixtures/
git commit -m "docs: document Talk bot compatibility requirements"
```

---

### Task 3: Define the external Hermes plugin contract

**Objective:** Use Hermes’s supported external-plugin mechanism rather than patching Hermes core.

**Files:**
- Create: `plugin.yaml`
- Create: `src/hermes_nextcloud_talk/__init__.py`
- Create: `src/hermes_nextcloud_talk/plugin.py`
- Create: `tests/test_plugin_contract.py`
- Create: `docs/architecture.md`

**Steps:**
1. Inspect the current Hermes external plugin manifest and registration APIs from the installed Hermes version before writing the manifest.
2. Declare plugin metadata, required secret names, optional config, and platform kind.
3. Implement only the registration boundary required to let Hermes discover a platform adapter.
4. Add a contract test that imports the package and validates manifest fields without requiring credentials or network access.
5. Document the exact supported Hermes versions tested.

**Verification:**
```bash
uv run pytest tests/test_plugin_contract.py -v
# In a throwaway HERMES_HOME, install/enable the plugin and verify discovery.
```

**Commit:**
```bash
git add plugin.yaml src/hermes_nextcloud_talk tests/test_plugin_contract.py docs/architecture.md
git commit -m "feat: add Hermes plugin registration skeleton"
```

---

### Task 4: Implement strict configuration validation

**Objective:** Fail closed on unsafe/missing configuration before accepting webhook traffic.

**Files:**
- Create: `src/hermes_nextcloud_talk/config.py`
- Create: `tests/test_config.py`
- Create: `examples/config.single-profile.yaml`

**Steps:**
1. Write failing tests for required base URL, bot secret, profile name, webhook host/port, and safe defaults.
2. Implement Pydantic settings/models.
3. Reject an empty user and room policy unless `allow_all_users: true` is explicitly configured for development.
4. Require `require_mention: true` by default for group traffic.
5. Reject non-HTTPS public callback URLs in production mode; allow localhost only for controlled development/test mode.
6. Ensure validation errors never echo secret values.

**Verification:**
```bash
uv run pytest tests/test_config.py -v
uv run ruff check src/hermes_nextcloud_talk/config.py tests/test_config.py
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/config.py tests/test_config.py examples/config.single-profile.yaml
git commit -m "feat: validate Nextcloud Talk configuration"
```

---

### Task 5: Implement webhook signature and replay protection

**Objective:** Authenticate Talk before parsing or dispatching payloads.

**Files:**
- Create: `src/hermes_nextcloud_talk/signing.py`
- Create: `src/hermes_nextcloud_talk/replay.py`
- Create: `tests/test_signing.py`
- Create: `tests/test_replay.py`

**Steps:**
1. Write fixed-vector tests for valid signatures, altered bodies, altered random values, missing headers, malformed hex, and wrong secret.
2. Implement constant-time comparison with `hmac.compare_digest`.
3. Store short-lived hashes of accepted `(random, body digest)` values in a bounded TTL cache; reject duplicates within the configured replay window.
4. Define clear non-secret error categories: invalid signature, malformed request, replayed request, unauthorized sender.
5. Log only request metadata/digests, never the raw secret or body by default.

**Verification:**
```bash
uv run pytest tests/test_signing.py tests/test_replay.py -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/signing.py src/hermes_nextcloud_talk/replay.py tests/
git commit -m "feat: verify Talk webhooks and prevent replay"
```

---

### Task 6: Parse and normalize Nextcloud Talk events

**Objective:** Convert trusted Talk ActivityStreams-style webhooks into a typed internal message model.

**Files:**
- Create: `src/hermes_nextcloud_talk/models.py`
- Create: `src/hermes_nextcloud_talk/parser.py`
- Create: `tests/test_parser.py`
- Create: sanitized fixtures under `tests/fixtures/`

**Steps:**
1. Write tests for normal messages, rich-object content, reply events (`object.inReplyTo`), non-message/system events, bot-added, bot-removed, malformed content, and unknown event types.
2. Parse `object.content` as its nested JSON dictionary and preserve plain text plus safe metadata.
3. Extract sender ID, sender display name, room token, room name, inbound message ID, parent/reply ID, optional thread metadata, and media type.
4. Explicitly ignore messages authored by the same bot to prevent reply loops.
5. Normalize all identifiers as opaque strings; never use a display name as an authorization identity.

**Verification:**
```bash
uv run pytest tests/test_parser.py -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/models.py src/hermes_nextcloud_talk/parser.py tests/
git commit -m "feat: normalize Nextcloud Talk bot events"
```

---

### Task 7: Add authorization and mention gating for group rooms

**Objective:** Allow only explicitly approved users/rooms to invoke Hermes, and keep group chats quiet unless addressed.

**Files:**
- Create: `src/hermes_nextcloud_talk/mentions.py`
- Create: `tests/test_mentions.py`
- Modify: `src/hermes_nextcloud_talk/config.py`
- Modify: `docs/configuration.md`

**Steps:**
1. Write tests for room allowlists, user allowlists, denied users, denied rooms, DM exception policy, direct bot replies, and mention regexes.
2. Implement an authorization function that receives typed event metadata and configuration only.
3. Implement mention detection on plain-text content with configurable regular expressions.
4. Strip only the leading addressed mention before forwarding user content to Hermes; retain raw content in local non-secret processing when needed for audit.
5. Return HTTP success for denied traffic to avoid giving unauthorized callers an oracle; do not trigger Hermes.

**Verification:**
```bash
uv run pytest tests/test_mentions.py -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/mentions.py tests/test_mentions.py src/hermes_nextcloud_talk/config.py docs/configuration.md
git commit -m "feat: authorize Talk users and gate group mentions"
```

---

### Task 8: Implement profile-safe session routing

**Objective:** Map a Talk room/thread to a stable session inside exactly one Hermes profile.

**Files:**
- Create: `src/hermes_nextcloud_talk/session_router.py`
- Create: `tests/test_session_router.py`
- Modify: `docs/architecture.md`
- Create: `docs/threads-and-topics.md`

**Steps:**
1. Write tests for root-room routing, two rooms, two threads in one room, no-thread fallback, profile prefixes, stable repeat routing, and invalid identifiers.
2. Implement the canonical session key:
   ```text
   nextcloud-talk:{profile}:{room-token}:{thread-id-or-root}
   ```
3. Use `target.id` as the room token and only use a verified thread ID when capability/event support is confirmed.
4. Fall back to `root` per room when Talk does not expose threads.
5. Document that Talk threads are similar to Telegram topics for session isolation but are not declared feature-parity until live tested.

**Verification:**
```bash
uv run pytest tests/test_session_router.py -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/session_router.py tests/test_session_router.py docs/
git commit -m "feat: route Talk rooms and threads to Hermes sessions"
```

---

### Task 9: Implement profile-safe Hermes invocation

**Objective:** Deliver normalized input to the selected profile and receive a response without crossing profile boundaries.

**Files:**
- Create: `src/hermes_nextcloud_talk/profile_runner.py`
- Create: `tests/test_profile_runner.py`
- Modify: `src/hermes_nextcloud_talk/adapter.py`

**Steps:**
1. Inspect current Hermes gateway/platform adapter interfaces and choose one supported call path.
2. Prefer the native gateway dispatcher/session pipeline if an external plugin has access to it; otherwise invoke a bounded `hermes -p <profile> chat ...` process with explicit session identity and timeout.
3. Do not use shell interpolation for message text or profile names; use argument arrays/subprocess APIs.
4. Add a process timeout and user-safe error response path.
5. Add test doubles for the Hermes boundary; unit tests must not run an LLM.
6. Add an integration test behind an opt-in environment variable for a real local Hermes test profile.

**Verification:**
```bash
uv run pytest tests/test_profile_runner.py -v
HERMES_NEXTCLOUD_TALK_LIVE_HERMES_TEST=1 uv run pytest -m integration -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/profile_runner.py src/hermes_nextcloud_talk/adapter.py tests/
git commit -m "feat: dispatch Talk messages to isolated Hermes profiles"
```

---

### Task 10: Implement outbound Talk bot client

**Objective:** Send Hermes replies back to the originating room, reply chain, and supported thread.

**Files:**
- Create: `src/hermes_nextcloud_talk/talk_client.py`
- Create: `tests/test_talk_client.py`

**Steps:**
1. Write tests using `httpx.MockTransport` for URL construction, mandatory headers, signature generation, success, 400, 401, 404, 413, 429, and retry behavior.
2. Create request signatures according to Nextcloud Talk’s outbound bot requirements using a fresh random value per request.
3. Send the response to `/ocs/v2.php/apps/spreed/api/v1/bot/{conversation-token}/message` with `OCS-APIRequest: true`.
4. Use `replyTo` when the inbound message is replyable and the behavior is enabled.
5. Add thread parameters only after Task 2 proves the correct bot API contract. Otherwise leave a documented capability-gated stub.
6. Truncate/chunk output safely based on server-advertised or configured message length. Preserve ordering and annotate continuation chunks.

**Verification:**
```bash
uv run pytest tests/test_talk_client.py -v
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/talk_client.py tests/test_talk_client.py
git commit -m "feat: send Hermes replies through Talk bot API"
```

---

### Task 11: Build inbound HTTP app and adapter lifecycle

**Objective:** Expose a safe webhook endpoint and wire all processing components together.

**Files:**
- Create: `src/hermes_nextcloud_talk/app.py`
- Create: `src/hermes_nextcloud_talk/adapter.py`
- Create: `src/hermes_nextcloud_talk/logging.py`
- Create: `tests/test_webhook_app.py`

**Steps:**
1. Write ASGI/integration tests for health endpoint, signature rejection, replay rejection, authorization skip, successful dispatch, Hermes error, Talk outbound error, and unhandled exceptions.
2. Add a `/healthz` endpoint containing no secrets and no user information.
3. Ensure body size limits are enforced before JSON parsing.
4. Process one inbound message idempotently; use `object.id`/reference IDs where available to avoid duplicate answers on webhook retries.
5. Configure structured logging with redaction of `Authorization`, secrets, HMAC headers, and message body by default.
6. Bind loopback by default. Document reverse-proxy/TLS deployment; do not make a public listener the default.

**Verification:**
```bash
uv run pytest tests/test_webhook_app.py -v
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk tests/
git commit -m "feat: expose secure Nextcloud Talk webhook service"
```

---

### Task 12: Add plugin CLI and operator diagnostics

**Objective:** Give administrators a predictable setup/verification interface.

**Files:**
- Create: `src/hermes_nextcloud_talk/cli.py`
- Modify: `pyproject.toml`
- Create: `docs/troubleshooting.md`
- Create: `docs/hermes-installation.md`

**CLI target:**

```bash
hermes-nextcloud-talk check
hermes-nextcloud-talk serve
hermes-nextcloud-talk capabilities
hermes-nextcloud-talk doctor
```

**Steps:**
1. Implement `check` to validate local config only, without exposing secrets.
2. Implement `capabilities` to query and summarize Talk version/capability support when credentials and a server are configured.
3. Implement `doctor` to check DNS/HTTPS reachability, local listener, expected Hermes binary/profile, and required config.
4. Implement `serve` with a clear production warning when bound beyond loopback without reverse proxy/TLS controls.
5. Document external plugin installation into the active Hermes profile and gateway restart steps.

**Verification:**
```bash
uv run hermes-nextcloud-talk check
uv run hermes-nextcloud-talk --help
```

**Commit:**
```bash
git add src/hermes_nextcloud_talk/cli.py pyproject.toml docs/
git commit -m "feat: add operator diagnostics CLI"
```

---

### Task 13: End-to-end single-profile smoke test

**Objective:** Prove a real Talk group message reaches one Hermes profile and receives a reply.

**Files:**
- Create: `docs/smoke-test.md`
- Modify: `docs/nextcloud-admin-setup.md`

**Steps:**
1. Create a dedicated non-production Nextcloud Talk bot, room, and allowlisted test user.
2. Deploy the webhook listener behind HTTPS, with the callback URL reachable from the Nextcloud server.
3. Install/add the bot via Nextcloud administrator `occ` commands.
4. Start a dedicated test Hermes profile and plugin service.
5. Send a non-mentioned group message; verify no Hermes reply.
6. Send a mentioned message; verify exactly one reply to the same room.
7. Send a follow-up; verify the same session key is used.
8. Send a message in a different room; verify it creates a different session.
9. If threads are available: create two threads and verify separate session keys and correct reply placement. If not, explicitly mark feature as unavailable on that server.
10. Rotate the bot secret after testing and verify old signed requests fail.

**Verification evidence to retain outside the repository:** sanitized timestamps, version/capabilities output, screen captures without tokens, and test results.

**Commit:**
```bash
git add docs/smoke-test.md docs/nextcloud-admin-setup.md
git commit -m "docs: add end-to-end Talk smoke test"
```

---

### Task 14: Prepare public release quality

**Objective:** Make the repo maintainable by other users and contributors.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Steps:**
1. Run CI on Python 3.10–3.13: tests, coverage threshold, ruff, package build.
2. Add Dependabot for GitHub Actions and Python dependencies.
3. Add user-facing install, upgrade, compatibility, security, and uninstall docs.
4. State the exact tested Hermes and Nextcloud Talk versions.
5. Add a compatibility table separating confirmed support from planned support.
6. Tag `v0.1.0` only after the live smoke test and CI pass.
7. Consider PyPI only after versioned releases are repeatable; use trusted publishing, never long-lived PyPI tokens in the repo.

**Verification:**
```bash
uv build
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

**Commit:**
```bash
git add .github README.md CHANGELOG.md
git commit -m "chore: prepare initial open source release"
```

---

## 6. Multi-profile and group-chat roadmap

### Supported in v0.1

Use one Nextcloud Talk bot configuration per Hermes profile. Add several bots to the same Talk group room:

```text
@Frank      → Hermes profile frank
@Researcher → Hermes profile researcher
@Trader     → Hermes profile trader
```

Each bot gets:

- Its own webhook secret.
- Its own callback endpoint/path or listener port.
- Its own Hermes profile invocation.
- Its own group mention patterns.
- Its own stable room/thread session namespace.

This is the simplest model, preserves Hermes isolation, and makes the identity of each agent visible in Talk.

### Planned after v0.1: router mode

One Talk bot receives all messages and dispatches based on explicit mention patterns:

```text
@frank investigate gateway status
@researcher summarize this document
@trader identify market movers
```

Rules:

- Require a unique mention match; ambiguous/multiple profile mentions must ask for clarification or intentionally fan out under an explicit configuration.
- Process every routed profile independently and label outbound replies.
- Do not grant router-mode traffic access to all profiles by default; configure an explicit profile allowlist.
- Enforce per-profile concurrency limits, timeouts, and queueing.
- Maintain room/thread-to-profile mapping after the first routed message so follow-ups can be handled naturally.

### Group-chat policy defaults

```yaml
require_mention: true
reply_to_bot_messages: true
allow_direct_messages: true
allow_all_users: false
allowed_rooms: []
allowed_users: []
```

A production installation must fill at least one allowlist. Open public invocation is never a default.

---

## 7. Threads / Telegram-topics design

### Capability-gated behavior

1. Query Talk server capabilities at startup and on a timed refresh.
2. If `threads` is unavailable, use one Hermes session per Talk room:
   ```text
   nextcloud-talk:{profile}:{room}:root
   ```
3. If `threads` is available and incoming event metadata provides a thread ID, use:
   ```text
   nextcloud-talk:{profile}:{room}:{thread}
   ```
4. Only create/send a Talk thread after the live spike proves exact bot endpoint fields and client behavior.
5. Expose diagnostic output:
   ```text
   threads: supported | unsupported | detected-but-unverified
   ```

### Do not overpromise

Talk threads are a plausible equivalent to Telegram topics for Hermes session isolation, but the project must document them as “capability-gated” until tested against each supported server version. Native Talk thread UI and Telegram forum-topic UI are not guaranteed to be identical.

---

## 8. Security and operations checklist

- [ ] Never commit `.env`, app passwords, bot secrets, room tokens, webhook URLs containing secret paths, or raw production fixtures.
- [ ] Use constant-time HMAC comparison.
- [ ] Require valid signatures before parsing payload or invoking Hermes.
- [ ] Add replay detection and idempotency.
- [ ] Require room/user allowlists in production.
- [ ] Enable mention gating in group rooms by default.
- [ ] Ignore self-authored bot events to prevent loops.
- [ ] Bound request body size, message size, subprocess time, outbound retries, queue depth, and log retention.
- [ ] Keep each Hermes profile isolated; no direct cross-profile data reads/writes.
- [ ] Bind locally by default; terminate TLS at a hardened reverse proxy; document firewall rules.
- [ ] Provide secret rotation instructions and a `doctor` command.
- [ ] Version the plugin independently from Hermes and document compatibility boundaries.

---

## 9. Open questions to answer before implementation is considered complete

1. Which exact Nextcloud and Talk versions will be the first supported target?
2. Does the intended Nextcloud server have administrator `occ` access to install Talk bots?
3. Can the Nextcloud server reach a stable HTTPS callback URL? If not, choose a deployment location/tunnel/reverse proxy before live testing.
4. How does the installed Talk version expose thread identity to webhook bots, and which outbound bot fields preserve it?
5. Does Hermes’s current external plugin API offer a direct profile-safe gateway dispatch hook, or should v0.1 use an isolated CLI/API runner?
6. Is the first public deployment one profile/one bot, or multiple bots in a group room?
7. What license and governance policy should apply to external contributions beyond MIT licensing?

---

## 10. Initial GitHub issue breakdown

Create these issues before coding so the work is trackable and reviewable:

1. `chore: scaffold Python package and developer tooling`
2. `research: validate Nextcloud Talk bot API against a live server`
3. `feat: register Hermes external platform plugin`
4. `feat: validate plugin configuration securely`
5. `feat: verify signed Talk webhooks and prevent replay`
6. `feat: normalize Talk webhook messages`
7. `feat: add room/user authorization and mention gating`
8. `feat: route rooms and threads to Hermes sessions`
9. `feat: invoke isolated Hermes profiles`
10. `feat: send replies through Nextcloud Talk bot API`
11. `feat: wire secure webhook service and adapter lifecycle`
12. `docs: add Nextcloud administrator deployment guide`
13. `test: complete live single-profile smoke test`
14. `chore: add CI, release process, and contribution templates`
15. `epic: add multi-profile router mode`
16. `epic: add capability-gated Talk thread/topic support`

---

## Definition of Done for v0.1

- Public GitHub repository has a clear README, MIT license, security policy, contributor guide, CI, and issue templates.
- Fresh install instructions work in a clean environment.
- A Talk administrator can install a bot and point it at the documented HTTPS endpoint.
- Plugin rejects invalid HMAC/replay/unauthorized traffic.
- An allowed user can mention the bot in a group room and receive one response in the same room.
- Separate Talk rooms create separate Hermes sessions.
- A single configured Hermes profile remains isolated from all others.
- Capability diagnostics accurately report whether threads are usable; threads are either proven in a live test or transparently documented as unavailable.
- Automated tests and lint pass, package builds, and a documented live smoke test passes.
