#!/usr/bin/env bash
# Deploy the email processor to Cloud Run and let it invoke the chatbot.
# The gmail token arrives as a Secret Manager volume on the same path the
# local docker-run mounts it, so the code is identical in both environments.
set -euo pipefail
cd "$(dirname "$0")"
source ./00-vars.sh
cd ..

CHATBOT_URL="$(gcloud run services describe chatbot --project="${PROJECT_ID}" \
  --region="${REGION}" --format="value(status.url)")"
echo "Chatbot URL: ${CHATBOT_URL}"

gcloud run services add-iam-policy-binding chatbot \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --member="serviceAccount:${SA_PROCESSOR}" \
  --role="roles/run.invoker" --quiet >/dev/null
echo "sa-email-processor: run.invoker on chatbot granted"

gcloud run deploy email-processor \
  --source . \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA_PROCESSOR}" \
  --no-allow-unauthenticated \
  --set-secrets="/secrets/gmail-token.json=gmail-token:latest" \
  --set-env-vars="GMAIL_TOKEN_PATH=/secrets/gmail-token.json,STATE_BACKEND=firestore,CHATBOT_URL=${CHATBOT_URL},CHATBOT_AUTH=true,PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/gmail-notifications" \
  --max-instances=2

gcloud run services describe email-processor --project="${PROJECT_ID}" \
  --region="${REGION}" --format="value(status.url)"
