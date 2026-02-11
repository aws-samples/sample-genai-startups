variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "retail-demo-eks"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "demo"
}

variable "domain_name" {
  description = "Domain name for SSL certificate (optional)"
  type        = string
  default     = ""
}

variable "allowed_management_cidrs" {
  description = "List of CIDR blocks allowed to access EKS cluster API endpoint. Defaults to 0.0.0.0/0 for backward compatibility. For production, restrict to specific IPs (e.g., ['10.0.0.0/8', '203.0.113.0/24'])"
  type        = list(string)
  default     = ["0.0.0.0/0"]
  
  validation {
    condition = alltrue([
      for cidr in var.allowed_management_cidrs : can(cidrhost(cidr, 0))
    ])
    error_message = "All values must be valid CIDR blocks (e.g., '10.0.0.0/8' or '192.168.1.1/32')."
  }
}