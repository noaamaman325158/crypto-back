resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"  # Immutable tags — images can't be overwritten

  image_scanning_configuration {
    scan_on_push = true  # Automatic vulnerability scanning on every push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_url" { value = aws_ecr_repository.app.repository_url }
output "repository_arn" { value = aws_ecr_repository.app.arn }
