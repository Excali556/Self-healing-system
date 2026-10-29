terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance size (t3.micro/t3.medium)"
  type        = string
  default     = "t3.medium"
}

# --- ECR Repositories ---
resource "aws_ecr_repository" "nexus_app" {
  name                 = "nexus-app"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "nexus_healer" {
  name                 = "nexus-healer"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "nexus_chaos" {
  name                 = "nexus-chaos"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "nexus_dashboard" {
  name                 = "nexus-dashboard"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Security Group ---
resource "aws_security_group" "nexus_sg" {
  name        = "nexus-cluster-sg"
  description = "Ingress for Nexus Observability, App, and Healer"

  ingress {
    description = "SSH access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Streamlit Resilience Dashboard"
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Grafana Dashboards"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Prometheus TSDB"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "FastAPI Victim App"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Nexus Autonomous Healer API"
    from_port   = 5050
    to_port     = 5050
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

# --- IAM Role for EC2 CloudWatch & ECR Access ---
resource "aws_iam_role" "nexus_ec2_role" {
  name = "nexus-ec2-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cw_policy" {
  role       = aws_iam_role.nexus_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy_attachment" "ecr_policy" {
  role       = aws_iam_role.nexus_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "nexus_profile" {
  name = "nexus-ec2-profile"
  role = aws_iam_role.nexus_ec2_role.name
}

# --- CloudWatch Log Group & Alarms ---
resource "aws_cloudwatch_log_group" "nexus_incidents" {
  name              = "/nexus/resilience/incidents"
  retention_in_days = 14
}

resource "aws_sns_topic" "resilience_alerts" {
  name = "nexus-resilience-incident-alerts"
}

output "streamlit_url" {
  description = "Nexus Streamlit UI"
  value       = "http://<EC2_PUBLIC_IP>:8501"
}

output "grafana_url" {
  description = "Nexus Grafana UI"
  value       = "http://<EC2_PUBLIC_IP>:3000"
}
