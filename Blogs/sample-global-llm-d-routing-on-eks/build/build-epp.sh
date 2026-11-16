#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Build the EPP image with cluster-itl-scorer in CodeBuild and push it to ECR.
# It clones upstream llm-d-router at $LLMD_ROUTER_REF, adds the plugin, applies the runner patch,
# zips the result to S3 and runs CodeBuild (go vet + go test + docker build + push).
# Usage: build/build-epp.sh <image-tag>
set -euo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
TAG=$1; R=$REGION; REPO=$ACCOUNT_ID.dkr.ecr.$R.amazonaws.com/$EPP_REPO
WORK=$(mktemp -d)
git clone -q --depth 1 --branch "$LLMD_ROUTER_REF" https://github.com/llm-d/llm-d-router.git "$WORK/src"
cp -R llm-d-router-plugin/pkg/. "$WORK/src/pkg/"
git -C "$WORK/src" apply "$PWD/llm-d-router-plugin/runner.go.patch"
cp build/buildspec-epp.yml "$WORK/src/buildspec.yml"
( cd "$WORK/src" && zip -qr "$WORK/epp-src.zip" . -x '.git/*' )
aws s3 cp --quiet "$WORK/epp-src.zip" "s3://$BUILD_BUCKET/epp-src.zip"
aws codebuild create-project --region $R --name gr-epp --source type=S3,location=$BUILD_BUCKET/epp-src.zip \
  --artifacts type=NO_ARTIFACTS --service-role arn:aws:iam::$ACCOUNT_ID:role/$CODEBUILD_ROLE \
  --environment type=LINUX_CONTAINER,image=aws/codebuild/standard:7.0,computeType=BUILD_GENERAL1_LARGE,privilegedMode=true \
  --tags key=project,value=global-routing >/dev/null 2>&1 || true
ID=$(aws codebuild start-build --region $R --project-name gr-epp \
  --environment-variables-override name=IMAGE_TAG,value=$TAG name=REPO,value=$REPO \
  --query build.id --output text)
echo "build $ID"
while :; do S=$(aws codebuild batch-get-builds --region $R --ids $ID --query 'builds[0].buildStatus' --output text); [[ $S != IN_PROGRESS ]] && break; sleep 20; done
echo "status $S"
G=$(aws codebuild batch-get-builds --region $R --ids $ID --query 'builds[0].logs.[groupName,streamName]' --output text)
aws logs get-log-events --region $R --log-group-name $(echo $G | cut -d' ' -f1) --log-stream-name $(echo $G | cut -d' ' -f2) --query 'events[].message' --output text | tail -40
rm -rf "$WORK"
[[ $S == SUCCEEDED ]]
