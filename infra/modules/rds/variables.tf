variable "project_name" {}
variable "environment" {}
variable "db_password" { sensitive = true }
variable "subnet_ids" { type = list(string) }
variable "vpc_id" {}
variable "app_sg_id" {}
variable "worker_sg_id" { default = "" }
