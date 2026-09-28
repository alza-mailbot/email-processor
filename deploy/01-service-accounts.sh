#!/usr/bin/env bash
# Create the three least-privilege service accounts and their project roles.
# Cross-service permissions (run.invoker) are granted after the services exist.
set -euo pipefail
cd "$(dirname "$0")"
source ./00-vars.sh

create_sa() {
  local name="$1" display="$2"
  if gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" \
      --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "SA ${name} already exists"
  else
    gcloud iam service-accounts create "${name}" \
      --project="${PROJECT_ID}" --display-name="${display}"
  fi
}

create_sa sa-chatbot "Chatbot service (Vertex AI)"
create_sa sa-email-processor "Email processor service"
create_sa sa-pubsub-push "Pub/Sub push + Scheduler invoker"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_CHATBOT}" \
  --role="roles/aiplatform.user" --condition=None --quiet >/dev/null
echo "sa-chatbot: aiplatform.user granted"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_PROCESSOR}" \
  --role="roles/datastore.user" --condition=None --quiet >/dev/null
echo "sa-email-processor: datastore.user granted"

echo "Done. Verify with: gcloud iam service-accounts list --project=${PROJECT_ID}"
