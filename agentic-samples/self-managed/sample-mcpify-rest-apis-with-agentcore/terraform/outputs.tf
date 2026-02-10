output "cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  description = "Security group ids attached to the cluster control plane"
  value       = module.eks.cluster_security_group_id
}

output "cluster_name" {
  description = "Kubernetes Cluster Name"
  value       = module.eks.cluster_name
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "vpc_id" {
  description = "ID of the VPC where the cluster is deployed"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "List of IDs of private subnets"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "List of IDs of public subnets"
  value       = module.vpc.public_subnets
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.retail_data.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.retail_data.arn
}

output "retail_api_irsa_role_arn" {
  description = "ARN of the IAM role for retail API service account"
  value       = aws_iam_role.retail_api_irsa.arn
}

output "retail_api_service_account_name" {
  description = "Name of the Kubernetes service account"
  value       = kubernetes_service_account.retail_api.metadata[0].name
}

output "eks_cluster_endpoint_access" {
  description = "EKS cluster endpoint access configuration"
  value = {
    public_access_enabled = true
    public_access_cidrs   = var.allowed_management_cidrs
    private_access_enabled = true
  }
}

output "kms_key_id" {
  description = "ID of the customer-managed KMS key used for DynamoDB encryption"
  value       = aws_kms_key.dynamodb.key_id
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used for DynamoDB encryption"
  value       = aws_kms_key.dynamodb.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key for easy reference"
  value       = aws_kms_alias.dynamodb.name
}