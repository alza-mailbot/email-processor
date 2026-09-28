# List available recipes
default:
    @just --list

# Install dependencies
install:
    uv sync

# Run the development server with auto-reload
run:
    uv run uvicorn email_processor.main:app --host 0.0.0.0 --port 8081 --reload

# Run tests (pass extra args to pytest)
test *ARGS:
    uv run pytest {{ARGS}}

# Run unit tests
test-unit:
    uv run pytest tests/unit

# Run integration tests
test-integration:
    uv run pytest tests/integration

# Format code
format:
    uv run ruff format .

# Lint code
lint:
    uv run ruff check .

# Lint code and auto-fix
lint-fix:
    uv run ruff check --fix .

# Type-check code
type-check:
    uv run ty check

# Lint + type-check
check: lint type-check

# Format + lint with auto-fix
fix: format lint-fix

# Build the container image
docker-build:
    docker build -t email-processor .

# Run the container locally (ADC for Firestore; token mounted like the Cloud Run secret volume)
docker-run:
    docker run --rm -p 8081:8080 --env-file .env \
      --add-host=host.docker.internal:host-gateway \
      -e CHATBOT_URL=http://host.docker.internal:8080 \
      -e STATE_BACKEND=firestore \
      -v ~/.config/gcloud/application_default_credentials.json:/adc.json:ro \
      -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
      -v $(pwd)/token.json:/secrets/gmail-token.json:ro \
      -e GMAIL_TOKEN_PATH=/secrets/gmail-token.json \
      email-processor

# Install pre-commit hooks
install-hooks:
    uv run pre-commit install

# Run pre-commit checks on all files
pre-commit:
    uv run pre-commit run --all-files

# Remove caches
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    rm -rf .pytest_cache .ruff_cache

# Add a dependency
add PACKAGE:
    uv add {{PACKAGE}}

# Add a dev dependency
add-dev PACKAGE:
    uv add --dev {{PACKAGE}}

# Remove a dependency
remove PACKAGE:
    uv remove {{PACKAGE}}

# Sync environment exactly to the lockfile
sync-frozen:
    uv sync --frozen

# Upgrade dependencies and sync
update:
    uv sync --upgrade
