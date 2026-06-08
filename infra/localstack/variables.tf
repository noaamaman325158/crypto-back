variable "project_name"      { default = "crypto-back" }
variable "environment"       { default = "localstack" }
variable "image_tag"         { default = "test" }
variable "db_password"       { sensitive = true }
variable "secret_key"        { sensitive = true }
variable "internal_api_key"  { sensitive = true }
variable "anthropic_api_key" { sensitive = true }
variable "coingecko_api_key" {
  default   = ""
  sensitive = true
}
