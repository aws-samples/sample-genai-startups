terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

# VPC
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.13.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  enable_vpn_gateway = false
  enable_dns_hostnames = true
  enable_dns_support = true

  tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# EKS Cluster
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.31.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.33"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  
  # Cluster endpoint access configuration
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.allowed_management_cidrs
  cluster_endpoint_private_access      = true

  eks_managed_node_groups = {
    main = {
      name = "main"
      
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = ["t3.medium"]
      
      min_size     = 1
      max_size     = 3
      desired_size = 2

      disk_size = 50
      
      labels = {
        role = "main"
      }
    }
  }

  tags = {
    Environment = var.environment
    Project     = "retail-demo"
  }
}

# KMS Key for DynamoDB Encryption
resource "aws_kms_key" "dynamodb" {
  description             = "Customer-managed KMS key for DynamoDB RetailData table encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true
  
  tags = {
    Name        = "${var.cluster_name}-dynamodb-key"
    Environment = var.environment
    Project     = "retail-demo"
    ManagedBy   = "Terraform"
  }
}

resource "aws_kms_alias" "dynamodb" {
  name          = "alias/${var.cluster_name}-dynamodb"
  target_key_id = aws_kms_key.dynamodb.key_id
}

# DynamoDB Table for Retail Data
resource "aws_dynamodb_table" "retail_data" {
  name           = "RetailData"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.dynamodb.arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Environment = var.environment
    Project     = "retail-demo"
    ManagedBy   = "Terraform"
  }
}

# IAM Role for EKS Service Account (IRSA)
resource "aws_iam_role" "retail_api_irsa" {
  name = "${var.cluster_name}-retail-api-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" = "system:serviceaccount:retail-demo:retail-api-sa"
            "${module.eks.oidc_provider}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = {
    Environment = var.environment
    Project     = "retail-demo"
    ManagedBy   = "Terraform"
  }
}

# IAM Policy for DynamoDB Access
resource "aws_iam_role_policy" "retail_api_dynamodb" {
  name = "DynamoDBAccess"
  role = aws_iam_role.retail_api_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.retail_data.arn,
          "${aws_dynamodb_table.retail_data.arn}/index/GSI1"
        ]
      }
    ]
  })
}

# IAM Policy for KMS Decrypt Access
resource "aws_iam_role_policy" "retail_api_kms" {
  name = "KMSDecryptAccess"
  role = aws_iam_role.retail_api_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = [
          aws_kms_key.dynamodb.arn
        ]
      }
    ]
  })
}

# Kubernetes Service Account
resource "kubernetes_service_account" "retail_api" {
  metadata {
    name      = "retail-api-sa"
    namespace = "retail-demo"
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.retail_api_irsa.arn
    }
  }

  depends_on = [module.eks]
}