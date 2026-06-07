# Terraform provider override targeting LocalStack.
# Apply with:
#   terraform init
#   terraform apply -var-file=localstack.tfvars
#
# In CI this runs without real AWS credentials — LocalStack accepts "test"/"test".

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
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    iam            = "http://localhost:4566"
    sts            = "http://localhost:4566"
    ec2            = "http://localhost:4566"
    ecr            = "http://localhost:4566"
    ecs            = "http://localhost:4566"
    s3             = "http://localhost:4566"
    ssm            = "http://localhost:4566"
    logs           = "http://localhost:4566"
    elasticache    = "http://localhost:4566"
    rds            = "http://localhost:4566"
    elbv2          = "http://localhost:4566"
  }
}
