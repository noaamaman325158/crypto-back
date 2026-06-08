# Standalone Terraform config targeting LocalStack (local dev + CI only).
# Run from this directory:
#   cd infra/localstack
#   terraform init
#   terraform apply -var-file=../localstack.tfvars
#
# Kept separate from infra/ so the production config and LocalStack config
# never conflict. Terraform loads all *.tf in a directory — mixing two
# provider blocks in the same dir causes "Duplicate provider" errors.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test" # nosemgrep: terraform.aws.security.aws-provider-static-credentials.aws-provider-static-credentials
  secret_key                  = "test" # nosemgrep: terraform.aws.security.aws-provider-static-credentials.aws-provider-static-credentials
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

# Point all modules at LocalStack
module "networking" {
  source       = "../modules/networking"
  project_name = var.project_name
  environment  = var.environment
}

module "ecr" {
  source       = "../modules/ecr"
  project_name = var.project_name
}

module "rds" {
  source       = "../modules/rds"
  project_name = var.project_name
  environment  = var.environment
  db_password  = var.db_password
  subnet_ids   = module.networking.private_subnet_ids
  vpc_id       = module.networking.vpc_id
  app_sg_id    = module.ecs.app_security_group_id
}

module "elasticache" {
  source       = "../modules/elasticache"
  project_name = var.project_name
  subnet_ids   = module.networking.private_subnet_ids
  vpc_id       = module.networking.vpc_id
  app_sg_id    = module.ecs.app_security_group_id
}

module "iam" {
  source       = "../modules/iam"
  project_name = var.project_name
  ecr_arn      = module.ecr.repository_arn
}

module "ecs" {
  source             = "../modules/ecs"
  project_name       = var.project_name
  environment        = var.environment
  image_uri          = "${module.ecr.repository_url}:${var.image_tag}"
  execution_role_arn = module.iam.execution_role_arn
  task_role_arn      = module.iam.task_role_arn
  vpc_id             = module.networking.vpc_id
  public_subnet_ids  = module.networking.public_subnet_ids
  database_url       = "postgresql+asyncpg://postgres:${var.db_password}@${module.rds.endpoint}/crypto_db"
  redis_url          = "redis://${module.elasticache.endpoint}:6379"
  secret_key         = var.secret_key
  internal_api_key   = var.internal_api_key
  anthropic_api_key  = var.anthropic_api_key
  coingecko_api_key  = var.coingecko_api_key
  certificate_arn    = ""  # Not used in LocalStack — TLS handled externally in production
}
