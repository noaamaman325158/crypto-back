variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  default     = "crypto-back"
}

variable "environment" {
  description = "Deployment environment"
  default     = "production"
}

variable "image_tag" {
  description = "Docker image tag (git SHA) to deploy"
}

variable "db_username" {
  description = "PostgreSQL master username"
  default     = "postgres"
}

variable "db_password" {
  description = "PostgreSQL master password"
  sensitive   = true
}

variable "secret_key" {
  description = "JWT signing secret"
  sensitive   = true
}

variable "internal_api_key" {
  description = "Service-to-service API key"
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for AI insights"
  sensitive   = true
}

variable "coingecko_api_key" {
  description = "CoinGecko API key (optional)"
  default     = ""
  sensitive   = true
}
