#!/usr/bin/env bash
# Upload the Gmail OAuth token as a secret and let only the processor read it.
# Run from the email-processor repo root (where token.json lives); re-running
# after a token refresh adds a new secret version.
set -euo pipefail
cd "$(dirname "$0")"
source ./00-vars.sh
cd ..

[ -f token.json ] || { echo "token.json not found; run scripts/authorize.py first" >&2; exit 1; }

if gcloud secrets describe gmail-token --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets versions add gmail-token --project="${PROJECT_ID}" --data-file=token.json
else
  gcloud secrets create gmail-token --project="${PROJECT_ID}" \
    --replication-policy=automatic --data-file=token.json
fi

gcloud secrets add-iam-policy-binding gmail-token --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_PROCESSOR}" \
  --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
echo "sa-email-processor: secretAccessor on gmail-token granted"

echo "Done. Verify with: gcloud secrets versions list gmail-token --project=${PROJECT_ID}"
