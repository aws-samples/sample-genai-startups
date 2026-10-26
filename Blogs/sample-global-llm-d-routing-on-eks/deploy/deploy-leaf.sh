#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Deploy one leaf: GIE CRDs, simulator pods, llm-d router (EPP + Envoy), internal NLB.
# Usage: deploy-leaf.sh <kube-context>   (latency knobs via env, see defaults)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=$PWD/bin:$PATH KUBECONFIG=$PWD/infra/kubeconfig
CTX=$1; NS=llm-d
export SIM_REPLICAS=${SIM_REPLICAS:-3} MAX_SEQS=${MAX_SEQS:-16} TTFT=${TTFT:-150ms} TTFT_SD=${TTFT_SD:-20ms}
export ITL=${ITL:-20ms} ITL_SD=${ITL_SD:-3ms} LOAD_FACTOR=${LOAD_FACTOR:-2.0}

kubectl --context $CTX apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.6.2/v1-manifests.yaml >/dev/null
kubectl --context $CTX create ns $NS --dry-run=client -o yaml | kubectl --context $CTX apply -f - >/dev/null
envsubst < deploy/leaf/sim.yaml.tpl | kubectl --context $CTX -n $NS apply -f -
helm upgrade --install leaf oci://ghcr.io/llm-d/charts/llm-d-router-standalone --version v0.11.0 --kube-context $CTX -n $NS \
  -f deploy/leaf/leaf-router.values.yaml -f deploy/leaf/leaf.values.yaml -f deploy/small.values.yaml
kubectl --context $CTX -n $NS apply -f deploy/leaf/expose.yaml
kubectl --context $CTX -n $NS rollout status deploy/sim --timeout=300s
kubectl --context $CTX -n $NS rollout status deploy/leaf-epp --timeout=300s
