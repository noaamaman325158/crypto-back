variable "project_name" {}
variable "environment" {}
variable "image_uri" {}
variable "execution_role_arn" {}
variable "task_role_arn" {}
variable "vpc_id" {}
variable "vpc_cidr" { default = "10.0.0.0/16" }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "database_url" { sensitive = true }
variable "redis_url" {}
variable "secret_key" { sensitive = true }
variable "internal_api_key" { sensitive = true }
variable "anthropic_api_key" { sensitive = true }
variable "coingecko_api_key" { sensitive = true }
variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS listener. Required for production."
  default     = ""
}
