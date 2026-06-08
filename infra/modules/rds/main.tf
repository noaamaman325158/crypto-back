resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "rds" {
  name   = "${var.project_name}-rds-sg"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.app_sg_id]
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.micro"  # Free-tier eligible; upgrade to db.t3.small+ for prod
  allocated_storage      = 20
  db_name                = "crypto_db"
  username               = "postgres"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = var.environment != "production"
  storage_encrypted      = true
  deletion_protection    = var.environment == "production"

  # Production: set multi_az = true for HA; read replicas via aws_db_instance replica
  multi_az = false

  # Enable PostgreSQL logs — captures slow queries, connections, and errors.
  # Essential for auditing and incident response.
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}

output "endpoint" { value = aws_db_instance.postgres.address }
