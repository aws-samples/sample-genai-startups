#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Replace a leaf's simulator pods with real vLLM on its GPU nodes. Usage: swap-to-vllm.sh <ctx> [replicas]
set -euo pipefail
cd "$(dirname "$0")/.."
CTX=$1; export VLLM_REPLICAS=${2:-2} MODEL=${MODEL:-Qwen/Qwen2.5-1.5B-Instruct} MAX_SEQS=${MAX_SEQS:-32} DTYPE=${DTYPE:-auto}
envsubst < deploy/leaf/vllm.yaml.tpl | bin/k $CTX apply -f -
bin/k $CTX rollout status deploy/vllm --timeout=1500s
bin/k $CTX scale deploy/sim --replicas=0
bin/k $CTX patch svc sim-pods --type=json -p '[{"op":"replace","path":"/spec/selector","value":{"llm-d.ai/guide":"optimized-baseline"}}]' >/dev/null
# publisher: new pod selector already covers vllm pods; tell it the batch limit
bin/k $CTX set env deploy/publisher MAX_SEQS=$MAX_SEQS MODEL=$MODEL >/dev/null
