# Terraform provider override targeting LocalStack (local dev + CI only).
# Apply with:
#   terraform init
#   terraform apply -var-file=localstack.tfvars
#
# Credentials are intentionally dummy values — LocalStack does not validate them.
# This file is NOT used in production. Real AWS uses OIDC (no static credentials).
# nosemgrep: terraform.aws.security.aws-provider-static-credentials.aws-provider-static-credentials

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test" # LocalStack dummy — not a real credential
  secret_key                  = "test" # LocalStack dummy — not a real credential
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    iam         = "http://localhost:4566"
    sts         = "http://localhost:4566"
    ec2         = "http://localhost:4566"
    ecr         = "http://localhost:4566"
    ecs         = "http://localhost:4566"
    s3          = "http://localhost:4566"
    ssm         = "http://localhost:4566"
    logs        = "http://localhost:4566"
    elasticache = "http://localhost:4566"
    rds         = "http://localhost:4566"
    elbv2       = "http://localhost:4566"
  }
}
