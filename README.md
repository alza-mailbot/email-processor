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

## Development

| Command | Description |
| --- | --- |
| `just` | List all recipes |
| `just test` | Run all tests (`just test-unit`, `just test-integration` for subsets) |
| `just check` | Lint + type-check |
| `just fix` | Format + auto-fix lint issues |
| `just pre-commit` | Run all pre-commit checks manually |

Every commit runs ruff, ty and the full pytest suite via pre-commit hooks.

### Testing conventions

- Tests mirror the source tree and are split into `tests/unit/` and `tests/integration/`.
- TDD: tests are written before the implementation, covering both positive and negative cases.
- Tests marked `live` call real external services and run only via `uv run pytest -m live`.
