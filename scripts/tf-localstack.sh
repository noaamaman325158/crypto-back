#!/usr/bin/env bash
# Run Terraform against LocalStack (local dev).
# Usage: ./scripts/tf-localstack.sh [plan|apply|destroy]
set -euo pipefail

COMMAND=${1:-plan}
LOCALSTACK_ENDPOINT="http://localhost:4566"

echo "▶ Targeting LocalStack at $LOCALSTACK_ENDPOINT"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

# Override all sensitive vars with dummy values for LocalStack
export TF_VAR_db_password=localstack-db-pass
export TF_VAR_secret_key=localstack-secret-key
export TF_VAR_internal_api_key=localstack-api-key
export TF_VAR_anthropic_api_key=localstack-anthropic-key
export TF_VAR_image_tag=local-dev

cd "$(dirname "$0")/../infra"

terraform init -reconfigure
terraform "$COMMAND" -var-file=localstack.tfvars "$@"
