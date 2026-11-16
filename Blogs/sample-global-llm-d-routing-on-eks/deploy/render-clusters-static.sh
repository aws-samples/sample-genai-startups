#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Static clusters list from each leaf's NLB (first IP; cross-zone LB is on). Spike only; the registrar replaces this.
set -euo pipefail
cd "$(dirname "$0")/.."
ENTRIES=""
for CTX in "$@"; do
  H=$(bin/k $CTX get svc leaf-nlb -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
  IP=$(dig +short $H | sort | head -1)
  ENTRIES+="      - name: ${CTX#gr-}"$'\n'"        address: \"$IP\""$'\n'"        port: \"80\""$'\n'"        labels: {metricsAddress: \"$IP\", metricsPort: \"9090\"}"$'\n'
done
export ENTRIES
envsubst < deploy/hub/clusters.yaml.tpl | tee /dev/stderr | bin/k gr-hub apply -f -
