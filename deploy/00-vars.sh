# Shared variables for the deploy scripts; source this file, do not run it.

export PROJECT_ID="alza-mailbot-509813"
export REGION="europe-west3"

export SA_CHATBOT="sa-chatbot@${PROJECT_ID}.iam.gserviceaccount.com"
export SA_PROCESSOR="sa-email-processor@${PROJECT_ID}.iam.gserviceaccount.com"
export SA_PUBSUB="sa-pubsub-push@${PROJECT_ID}.iam.gserviceaccount.com"
