"""Test-wide environment setup.

Settings have required fields; tests provide dummy values up front so the
suite runs without a real token file or a local .env file.
"""

import os

os.environ.setdefault("GMAIL_TOKEN_PATH", "token.json")
os.environ.setdefault("CHATBOT_URL", "http://localhost:8080")
os.environ.setdefault("PUBSUB_TOPIC", "projects/test/topics/gmail")
os.environ.setdefault("RENEW_WATCH_ON_STARTUP", "false")
