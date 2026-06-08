resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

resource "aws_security_group" "app" {
  name   = "${var.project_name}-app-sg"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.project_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name  = "app"
    image = var.image_uri
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "DATABASE_URL",      value = var.database_url },
      { name = "REDIS_URL",         value = var.redis_url },
      { name = "ENVIRONMENT",       value = var.environment },
    ]
    secrets = [
      { name = "SECRET_KEY",         valueFrom = aws_ssm_parameter.secret_key.arn },
      { name = "INTERNAL_API_KEY",   valueFrom = aws_ssm_parameter.internal_api_key.arn },
      { name = "ANTHROPIC_API_KEY",  valueFrom = aws_ssm_parameter.anthropic_api_key.arn },
      { name = "COINGECKO_API_KEY",  valueFrom = aws_ssm_parameter.coingecko_api_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# Secrets stored in SSM Parameter Store (encrypted) — not in env vars or TF state
resource "aws_ssm_parameter" "secret_key" {
  name  = "/${var.project_name}/SECRET_KEY"
  type  = "SecureString"
  value = var.secret_key
}

resource "aws_ssm_parameter" "internal_api_key" {
  name  = "/${var.project_name}/INTERNAL_API_KEY"
  type  = "SecureString"
  value = var.internal_api_key
}

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/${var.project_name}/ANTHROPIC_API_KEY"
  type  = "SecureString"
  value = var.anthropic_api_key
}

resource "aws_ssm_parameter" "coingecko_api_key" {
  name  = "/${var.project_name}/COINGECKO_API_KEY"
  type  = "SecureString"
  value = var.coingecko_api_key
}

resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.app.id]
}

resource "aws_lb_target_group" "app" {
  name        = "${var.project_name}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check { path = "/health" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_ecs_service" "app" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

output "app_security_group_id" { value = aws_security_group.app.id }
output "load_balancer_dns"     { value = aws_lb.main.dns_name }
