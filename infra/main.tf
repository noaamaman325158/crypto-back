terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # In production: use S3 backend for shared state
  # backend "s3" {
  #   bucket = "your-tf-state-bucket"
  #   key    = "crypto-back/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source       = "./modules/networking"
  project_name = var.project_name
  environment  = var.environment
}

module "ecr" {
  source       = "./modules/ecr"
  project_name = var.project_name
}

module "rds" {
  source            = "./modules/rds"
  project_name      = var.project_name
  environment       = var.environment
  db_password       = var.db_password
  subnet_ids        = module.networking.private_subnet_ids
  vpc_id            = module.networking.vpc_id
  app_sg_id         = module.ecs.app_security_group_id
}

module "elasticache" {
  source       = "./modules/elasticache"
  project_name = var.project_name
  subnet_ids   = module.networking.private_subnet_ids
  vpc_id       = module.networking.vpc_id
  app_sg_id    = module.ecs.app_security_group_id
}

module "iam" {
  source       = "./modules/iam"
  project_name = var.project_name
  ecr_arn      = module.ecr.repository_arn
}

module "ecs" {
  source             = "./modules/ecs"
  project_name       = var.project_name
  environment        = var.environment
  image_uri          = "${module.ecr.repository_url}:${var.image_tag}"
  execution_role_arn = module.iam.execution_role_arn
  task_role_arn      = module.iam.task_role_arn
  vpc_id             = module.networking.vpc_id
  public_subnet_ids  = module.networking.public_subnet_ids
  database_url       = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${module.rds.endpoint}/crypto_db"
  redis_url          = "redis://${module.elasticache.endpoint}:6379"
  secret_key         = var.secret_key
  internal_api_key   = var.internal_api_key
  anthropic_api_key  = var.anthropic_api_key
  coingecko_api_key  = var.coingecko_api_key
  certificate_arn    = var.certificate_arn
}

output "app_url" {
  value = module.ecs.load_balancer_dns
}
