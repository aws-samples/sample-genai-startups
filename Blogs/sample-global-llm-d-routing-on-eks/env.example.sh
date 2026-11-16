# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Copy to env.sh and fill in. Every script sources ./env.sh from the repo root.
export ACCOUNT_ID=123456789012                 # AWS account for ECR, CodeBuild and S3
export REGION=us-east-2                        # hub region (ECR, CodeBuild, Valkey)
export EPP_REPO=gr/llm-d-epp                   # ECR repository for the custom EPP image
export EPP_TAG=clusteritl                      # image tag the hub deploys
export LLMD_ROUTER_REF=v0.11.0                 # upstream llm-d-router tag the plugin targets
export BUILD_BUCKET=my-build-bucket            # S3 bucket for the CodeBuild source zip
export CODEBUILD_ROLE=gr-codebuild             # IAM role CodeBuild runs as (ECR push, S3 read, logs)
export VALKEY_ENDPOINT=master.my-registry.xxxxxx.use2.cache.amazonaws.com   # registry primary endpoint
