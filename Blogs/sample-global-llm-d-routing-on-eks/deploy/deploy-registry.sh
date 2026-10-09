#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Deploy the registrar on the hub and a publisher on each leaf.
set -euo pipefail
# PUBLISHER_ONLY_CODE=1: only refresh publisher code (keeps per-leaf env such as MAX_SEQS/MODEL set by swap-to-vllm.sh)
cd "$(dirname "$0")/.."
source ./env.sh
export REDIS_HOST=$VALKEY_ENDPOINT MAX_SEQS=${MAX_SEQS:-16}
bin/k gr-hub create configmap registrar-py --from-file=registry/registrar.py --dry-run=client -o yaml | bin/k gr-hub apply -f -
envsubst '${VALKEY_ENDPOINT}' < deploy/registry/registrar.yaml | bin/k gr-hub apply -f -
for pair in gr-leaf-use2:us-east-2 gr-leaf-use1:us-east-1 gr-leaf-euw2:eu-west-2; do
  CTX=${pair%%:*}; export REGION=${pair##*:} CLUSTER=${CTX#gr-}
  export GATEWAY_HOST=$(bin/k $CTX get svc leaf-nlb -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
  bin/k $CTX create configmap publisher-py --from-file=registry/publisher.py --dry-run=client -o yaml | bin/k $CTX apply -f -
  [[ -z "${PUBLISHER_ONLY_CODE:-}" ]] && envsubst < deploy/registry/publisher.yaml.tpl | bin/k $CTX apply -f -
  bin/k $CTX rollout restart deploy/publisher
done
