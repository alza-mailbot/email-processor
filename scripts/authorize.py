#!/usr/bin/env python3
"""One-off interactive OAuth flow for the bot mailbox.

Opens a browser, lets you sign in as the bot account and writes the token
file the application reads at runtime. Requires credentials.json (the OAuth
client downloaded from the GCP console) in the working directory.

Usage:
    uv run python scripts/authorize.py [token_path]
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from email_processor.core.gmail.auth import SCOPES


def main() -> None:
    """Run the interactive flow and write the token file."""
    token_path = sys.argv[1] if len(sys.argv) > 1 else "token.json"
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())
    print(f"Token written to {token_path}")


if __name__ == "__main__":
    main()
