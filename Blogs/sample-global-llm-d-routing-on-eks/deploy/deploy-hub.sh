#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Deploy the hub router. Usage: deploy-hub.sh <policy>   (policy = load | latency | itl)
set -euo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
export PATH=$PWD/bin:$PATH KUBECONFIG=$PWD/infra/kubeconfig
CTX=gr-hub; NS=llm-d; POLICY=${1:-load}
kubectl --context $CTX apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.6.2/v1-manifests.yaml >/dev/null
kubectl --context $CTX create ns $NS --dry-run=client -o yaml | kubectl --context $CTX apply -f - >/dev/null
kubectl --context $CTX -n $NS get cm mc-hub-clusters >/dev/null 2>&1 || { echo "render clusters first"; exit 1; }
VALUES=$(mktemp)  # fill in account, image and Valkey placeholders
envsubst '${ACCOUNT_ID} ${REGION} ${EPP_REPO} ${EPP_TAG} ${VALKEY_ENDPOINT}' < deploy/hub/hub-$POLICY.values.yaml > $VALUES
helm upgrade --install hub oci://ghcr.io/llm-d/charts/llm-d-router-standalone --version v0.11.0 --kube-context $CTX -n $NS \
  -f deploy/hub/hub.values.yaml -f $VALUES -f deploy/small.values.yaml ${HUB_EXTRA:-}
kubectl --context $CTX -n $NS rollout status deploy/hub-epp --timeout=300s
