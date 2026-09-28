#!/usr/bin/env bash
# Point the Gmail push subscription at the Cloud Run processor and keep the
# watch alive with a daily Cloud Scheduler renewal. Both callers authenticate
# as sa-pubsub-push, the only identity on the processor's guest list.
set -euo pipefail
cd "$(dirname "$0")"
source ./00-vars.sh

PROCESSOR_URL="$(gcloud run services describe email-processor --project="${PROJECT_ID}" \
  --region="${REGION}" --format="value(status.url)")"
echo "Processor URL: ${PROCESSOR_URL}"

gcloud run services add-iam-policy-binding email-processor \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --member="serviceAccount:${SA_PUBSUB}" \
  --role="roles/run.invoker" --quiet >/dev/null
echo "sa-pubsub-push: run.invoker on email-processor granted"

# The Pub/Sub service agent mints the push OIDC tokens on behalf of
# sa-pubsub-push, so it needs permission to act as that account.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")"
gcloud iam service-accounts add-iam-policy-binding "${SA_PUBSUB}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" --quiet >/dev/null
echo "Pub/Sub service agent: tokenCreator on sa-pubsub-push granted"

# The ack deadline is how long Pub/Sub waits for our HTTP response before
# treating the delivery as failed. It must cover a full processing run
# (Gmail + Gemini), otherwise Pub/Sub redelivers early and produces
# duplicate work while the first attempt is still going. 300 mirrors the
# Cloud Run request timeout; raise both together or not at all.
gcloud pubsub subscriptions update gmail-push-sub \
  --project="${PROJECT_ID}" \
  --push-endpoint="${PROCESSOR_URL}/gmail-webhook" \
  --push-auth-service-account="${SA_PUBSUB}" \
  --ack-deadline=300 \
  --min-retry-delay=10s \
  --max-retry-delay=600s
echo "gmail-push-sub now pushes to ${PROCESSOR_URL}/gmail-webhook"

SCHEDULER_ARGS=(
  --project="${PROJECT_ID}" --location="${REGION}"
  --schedule="0 3 * * *" --time-zone="Europe/Prague"
  --http-method=POST --uri="${PROCESSOR_URL}/renew-watch"
  --oidc-service-account-email="${SA_PUBSUB}"
  --attempt-deadline=300s
)
if gcloud scheduler jobs describe renew-gmail-watch \
  --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http renew-gmail-watch "${SCHEDULER_ARGS[@]}"
else
  gcloud scheduler jobs create http renew-gmail-watch "${SCHEDULER_ARGS[@]}"
fi
echo "Scheduler job renew-gmail-watch ready (daily 03:00 Europe/Prague)"
