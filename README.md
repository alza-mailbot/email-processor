# Email processor

> Email processing service for the **alza-mailbot** system. It receives Gmail
> push notifications (via Pub/Sub), fetches new messages with their attachments
> and thread history, asks the `chatbot` service for a reply and sends it back
> within the original email thread.

It works alongside the `chatbot` service (sibling repository), which owns all
LLM interaction behind its `POST /v1/chat` contract.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python 3.14 automatically)
- [just](https://github.com/casey/just) task runner
- gcloud CLI with Application Default Credentials (`gcloud auth application-default login`)
- Gmail OAuth credentials for the bot mailbox (`credentials.json`, not committed)

## Setup

1. Install dependencies:
   ```bash
   just install
   ```
   *Done when:* `uv run python -c "import email_processor"` prints no error.
2. Create your local configuration:
   ```bash
   cp .env.sample .env
   ```
3. Install git hooks:
   ```bash
   just install-hooks
   ```
   *Done when:* `just pre-commit` passes on all files.

## Run

```bash
just run
```

The server listens on port **8081** so it can run next to the chatbot service (8080).

*Done when:* `curl localhost:8081/healthz` returns `{"status":"ok"}`.

## Local E2E

Full pipeline against the real mailbox, with both services on your machine:

1. Start the chatbot (port 8080, sibling repo) and this service:
   ```bash
   just run   # in each repository
   ```
   With `RENEW_WATCH_ON_STARTUP=true` the startup renews the Gmail watch and
   baselines (or catches up) the history pointer.
2. Expose the processor and point the Pub/Sub push subscription at it:
   ```bash
   cloudflared tunnel --url http://localhost:8081
   gcloud pubsub subscriptions update gmail-push-sub \
     --push-endpoint="https://<tunnel>.trycloudflare.com/gmail-webhook"
   ```
3. Send an email with text and a PDF attachment to the bot mailbox from a
   personal address. Within ~2 minutes a contextual reply arrives in the same
   thread and the message is marked read.
4. Reply in the same thread; the next answer takes the history into account.
5. Restart the processor and let Pub/Sub redeliver anything pending: no
   duplicate replies may appear (deduplication via the state file).

## Development

| Command | Description |
| --- | --- |
| `just` | List all recipes |
| `just run` | Start the dev server (auto-reload, port 8081) |
| `just test` | Run all tests (`just test-unit`, `just test-integration` for subsets) |
| `just check` | Lint + type-check |
| `just fix` | Format + auto-fix lint issues |
| `just pre-commit` | Run all pre-commit checks manually |
| `just docker-build` | Build the container image |
| `just docker-run` | Run the container (Firestore state, cloud-like mounts) |

Every commit runs ruff, ty and the full pytest suite via pre-commit hooks.

### Testing conventions

- Tests mirror the source tree and are split into `tests/unit/` and `tests/integration/`.
- TDD: tests are written before the implementation, covering both positive and negative cases.
- Tests marked `live` call real external services and run only via `uv run pytest -m live`.
