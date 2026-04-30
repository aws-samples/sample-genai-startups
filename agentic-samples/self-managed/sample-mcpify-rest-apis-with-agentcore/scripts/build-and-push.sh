#!/bin/bash

# Build and push Docker image to ECR
# Usage: ./build-and-push.sh [AWS_REGION] [ECR_REPOSITORY_NAME]

AWS_REGION=${1:-us-west-2}
ECR_REPO=${2:-retail-api}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Building Docker image..."
cd app
# Build for amd64 platform (required for EKS x86_64 nodes)
# Use buildx for multi-platform support
docker buildx build --platform linux/amd64 -t "$ECR_REPO:latest" .

echo "Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" || \
aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION"

echo "Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

echo "Tagging and pushing image..."
docker tag "$ECR_REPO:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"

echo "Image pushed successfully!"
echo "Update your deployment.yaml with: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"