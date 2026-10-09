#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# For each hub policy: deploy, warm up, then measure at each concurrency.
# Usage: POLICIES="load latency" CONCS="32 96" loadgen/matrix.sh <label>
set -uo pipefail
cd "$(dirname "$0")/.."
LABEL=${1:-m}
for P in ${POLICIES:-load latency itl-best-pod itl-predicted}; do
  deploy/deploy-hub.sh $P >/dev/null 2>&1 || { echo "deploy $P failed"; continue; }
  sleep 20
  TAG=warm-$P CONCURRENCY=${WARM_C:-32} REQUESTS=$(( ${WARM_C:-32} * 5 )) MAX_TOKENS=128 loadgen/run.sh >/dev/null
  for C in ${CONCS:-32 96}; do
    TAG=$LABEL-$P-c$C CONCURRENCY=$C REQUESTS=$((C*8)) MAX_TOKENS=${MAX_TOKENS:-256} loadgen/run.sh
  done
done
