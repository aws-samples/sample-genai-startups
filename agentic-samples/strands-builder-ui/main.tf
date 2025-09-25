terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.100.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"  # Change to your preferred region
}

# Variables
variable "app_name" {
  description = "Name of the application"
  default     = "strands-gui"
}

variable "environment" {
  description = "Deployment environment"
  default     = "dev"
}

variable "admin_email" {
  description = "Email for the default admin user"
  default     = "admin@example.com"
}


# Generate a random password for the database
resource "random_password" "db_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# ECR Repository
resource "aws_ecr_repository" "app_repo" {
  name                 = var.app_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Get current region
data "aws_region" "current" {}

# App Runner Service
resource "aws_apprunner_service" "app_service" {
  service_name = var.app_name

  source_configuration {
    auto_deployments_enabled = true
    image_repository {
      image_configuration {
        port = "5000"
        runtime_environment_variables = {
          # Set the database URI using the DSQL public endpoint
          # We'll need to update this with the actual identifier after the cluster is created
          SQLALCHEMY_DATABASE_URI = "${aws_dsql_cluster.strands_db.identifier}.dsql.${data.aws_region.current.name}.on.aws"
          # Cognito configuration
          COGNITO_ENABLED = "true"
          COGNITO_USER_POOL_ID = aws_cognito_user_pool.strands_user_pool.id
          COGNITO_CLIENT_ID = aws_cognito_user_pool_client.strands_client.id
          COGNITO_CLIENT_SECRET = ""
          COGNITO_DOMAIN = "${var.app_name}-${var.environment}.auth.${data.aws_region.current.name}.amazoncognito.com"
          # Use a placeholder that will be updated after deployment
          COGNITO_REDIRECT_URI = "https://placeholder-url.amazonaws.com/auth/callback"
          #OTEL_EXPORTER_OTLP_ENDPOINT="https://xray.us-east-1.amazonaws.com/v1/traces"
          #STRANDS_OTEL_ENABLE_CONSOLE_EXPORT=true

        }
      }
      image_identifier      = "${aws_ecr_repository.app_repo.repository_url}:latest"
      image_repository_type = "ECR"
    }
    authentication_configuration {
      access_role_arn = aws_iam_role.app_runner_access_role.arn
    }
  }

  # No network configuration - using default public egress

  # Set the instance role for the App Runner service
  instance_configuration {
    instance_role_arn = aws_iam_role.app_runner_instance_role.arn
    cpu               = "1024"
    memory            = "2048"
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.app_scaling.arn

  depends_on = [
    aws_ecr_repository.app_repo,
    null_resource.docker_push
  ]
}

# Auto Scaling Configuration for App Runner
resource "aws_apprunner_auto_scaling_configuration_version" "app_scaling" {
  auto_scaling_configuration_name = "${var.app_name}-scaling-config"
  max_concurrency                 = 100
  max_size                        = 1
  min_size                        = 1

  tags = {
    Name = "${var.app_name}-scaling-config"
  }
}

# IAM Role for App Runner ECR Access
resource "aws_iam_role" "app_runner_access_role" {
  name = "${var.app_name}-app-runner-access-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "build.apprunner.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Role for App Runner Instance
resource "aws_iam_role" "app_runner_instance_role" {
  name = "${var.app_name}-app-runner-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "tasks.apprunner.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for App Runner to pull from specific ECR repository
resource "aws_iam_policy" "ecr_access_policy" {
  name        = "${var.app_name}-ecr-access-policy"
  description = "Policy allowing access to specific ECR repository"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = aws_ecr_repository.app_repo.arn
      }
    ]
  })
}

# Attach AWS managed ECR policy to App Runner access role
resource "aws_iam_role_policy_attachment" "app_runner_ecr_policy" {
  role       = aws_iam_role.app_runner_access_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# IAM Policy for App Runner to access Amazon Bedrock
resource "aws_iam_policy" "bedrock_access_policy" {
  name        = "${var.app_name}-bedrock-access-policy"
  description = "Policy allowing minimal access to Amazon Bedrock services"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:ListInferenceProfiles",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:ListFoundationModels",
          "sts:GetCallerIdentity"
        ]
        Resource = "*"
      }
    ]
  })
}



# Attach Bedrock policy to App Runner instance role
resource "aws_iam_role_policy_attachment" "app_runner_bedrock_policy" {
  role       = aws_iam_role.app_runner_instance_role.name
  policy_arn = aws_iam_policy.bedrock_access_policy.arn
}

# IAM Policy for App Runner to access DSQL cluster
resource "aws_iam_policy" "dsql_access_policy" {
  name        = "${var.app_name}-dsql-access-policy"
  description = "Policy allowing minimal access to specific DSQL cluster"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dsql:DbConnect",
          "dsql:DbConnectAdmin"
        ]
        Resource = aws_dsql_cluster.strands_db.arn
      }
    ]
  })
}

# Attach DSQL policy to App Runner instance role
resource "aws_iam_role_policy_attachment" "app_runner_dsql_policy" {
  role       = aws_iam_role.app_runner_instance_role.name
  policy_arn = aws_iam_policy.dsql_access_policy.arn
}

# Attach AWSXrayWriteOnlyAccess policy to App Runner instance role
resource "aws_iam_role_policy_attachment" "app_runner_xray_policy" {
  role       = aws_iam_role.app_runner_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}

# Build and push Docker image
resource "null_resource" "docker_push" {
  triggers = {
    ecr_repository_url = aws_ecr_repository.app_repo.repository_url
    reqs = filemd5("${path.module}/requirements.txt")
    # Monitor all files in templates directory
    templates_hash = sha256(join("", [for f in fileset("${path.module}/templates", "**") : filemd5("${path.module}/templates/${f}")]))
    # Monitor all python files in root
    root_py_files_hash = sha256(join("", [for f in fileset("${path.module}", "*.py") : filemd5("${path.module}/${f}")]))
    # Monitor all files in static directory
    static_files_hash = sha256(join("", [for f in fileset("${path.module}/static", "**") : filemd5("${path.module}/static/${f}")]))
    # Monitor Dockerfile for changes
    df_py_hash = filemd5("${path.module}/Dockerfile")
  
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws ecr get-login-password --region ${data.aws_region.current.name} | podman login --username AWS --password-stdin ${aws_ecr_repository.app_repo.repository_url}
      podman build --platform=linux/amd64 -t ${aws_ecr_repository.app_repo.repository_url}:latest .
      podman push ${aws_ecr_repository.app_repo.repository_url}:latest
    EOT
  }

  depends_on = [aws_ecr_repository.app_repo]
}

# DSQL Cluster
resource "aws_dsql_cluster" "strands_db" {
  deletion_protection_enabled = false

  tags = {
    Name = "${var.app_name}-dsql-cluster"
  }
}

# Output the App Runner URL
output "app_url" {
  value = aws_apprunner_service.app_service.service_url
}

# Output instructions for updating Cognito callback URLs
output "update_cognito_instructions" {
  value = <<-EOT
    After deployment, update the Cognito client callback URLs with:
    
    aws cognito-idp update-user-pool-client \
      --user-pool-id ${aws_cognito_user_pool.strands_user_pool.id} \
      --client-id ${aws_cognito_user_pool_client.strands_client.id} \
      --callback-urls https://${aws_apprunner_service.app_service.service_url}/auth/callback \
      --logout-urls https://${aws_apprunner_service.app_service.service_url}/
  EOT
}

# Output the DSQL Cluster ARN
output "dsql_cluster_arn" {
  value = aws_dsql_cluster.strands_db.arn
  description = "The ARN of the DSQL cluster"
}

# Cognito User Pool
resource "aws_cognito_user_pool" "strands_user_pool" {
  name = "${var.app_name}-user-pool"
  
  username_attributes = ["email"]
  
  # Use verification configuration instead of auto_verify_attributes
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }
  
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
  
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }
  
  schema {
    attribute_data_type = "String"
    name                = "email"
    required            = true
    mutable             = true
  }
  
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
  
  tags = {
    Name = "${var.app_name}-user-pool-${var.environment}"
  }
}

# Cognito User Pool Client
resource "aws_cognito_user_pool_client" "strands_client" {
  name                = "${var.app_name}-client"
  user_pool_id        = aws_cognito_user_pool.strands_user_pool.id
  
  generate_secret     = false
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
  
  # Use a placeholder URL that will be updated later
  callback_urls       = ["https://placeholder-url.amazonaws.com/auth/callback"]
  logout_urls         = ["https://placeholder-url.amazonaws.com/"]
  
  allowed_oauth_flows = ["code"]
  allowed_oauth_scopes = ["email", "openid", "profile"]
  supported_identity_providers = ["COGNITO"]
}

# Create default admin user
resource "aws_cognito_user" "admin_user" {
  user_pool_id = aws_cognito_user_pool.strands_user_pool.id
  username     = var.admin_email
  
  attributes = {
    email          = var.admin_email
    email_verified = true
  }
}

# Generate a random password for the admin user
resource "random_password" "admin_password" {
  length           = 12
  special          = true
  override_special = "!@#$%^&*()-_=+[]{}:;<>,.?"
  min_numeric      = 1
}


# Output the admin password
output "admin_password" {
  value     = random_password.admin_password.result
  sensitive = true
  description = "Password for the admin user (sensitive)"
}

output "admin_user" {
  value     = "admin@example.com"
  description = "The default admin user"
}


# Set the admin user's password
resource "null_resource" "set_admin_password" {
  depends_on = [aws_cognito_user.admin_user]
  
  provisioner "local-exec" {
    command = <<-EOT
      aws cognito-idp admin-set-user-password \
        --user-pool-id ${aws_cognito_user_pool.strands_user_pool.id} \
        --username ${var.admin_email} \
        --password '${random_password.admin_password.result}' \
        --permanent
    EOT
  }
}
