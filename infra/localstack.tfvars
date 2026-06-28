# Use these values when running terraform against LocalStack locally or in CI.
# Never use real credentials here — LocalStack accepts any value.
aws_region        = "us-east-1"
project_name      = "crypto-back"
environment       = "localstack"
image_tag         = "test"
db_username       = "postgres"
db_password       = "postgres"
secret_key        = "localstack-secret-key"
internal_api_key  = "localstack-api-key"
anthropic_api_key = "localstack-anthropic-key"
coingecko_api_key = ""
certificate_arn   = "" # No real cert needed for LocalStack
