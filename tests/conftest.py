"""Test-wide environment setup.

Settings require GMAIL_TOKEN_PATH; tests provide a dummy value up front so the
suite runs without a real token file or a local .env file.
"""

import os

os.environ.setdefault("GMAIL_TOKEN_PATH", "token.json")
