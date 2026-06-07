# Override provider config when targeting LocalStack.
# Usage: terraform apply -var-file=localstack.tfvars
# Set TF_VAR_localstack=true or use this file explicitly.
#
# LocalStack endpoint: http://localhost:4566 (local) or http://localstack:4566 (docker-compose)

locals {
  localstack_endpoint = "http://localhost:4566"
}
