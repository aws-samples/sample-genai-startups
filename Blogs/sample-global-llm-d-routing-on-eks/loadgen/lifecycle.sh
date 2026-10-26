#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Kill or drain leaf-use2 in the middle of a steady load and see how the hub reacts.
# Usage: loadgen/lifecycle.sh graceful|crash
#   graceful: delete the publisher (SIGTERM -> DEL key), wait 3 s, then stop the leaf router.
#   crash:    force-kill the publisher and the leaf router at the same instant; the key must expire (TTL 10 s).
# Afterwards both are restored.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE=$1; LEAF=gr-leaf-use2
if [[ $MODE == crash ]]; then
  # A crashed publisher never runs its exit handler. Simulate that by turning the handler off first.
  bin/k $LEAF set env deploy/publisher DEREGISTER_ON_EXIT=false >/dev/null
  bin/k $LEAF rollout status deploy/publisher --timeout=120s >/dev/null; sleep 20
fi
TAG=life-$MODE CONCURRENCY=32 DURATION=75 MAX_TOKENS=128 loadgen/run.sh > results/life-$MODE.out &
LG=$!
sleep 45   # pip install + ~20 s of steady traffic
echo "$(date +%T) killing ($MODE) epoch=$(date +%s)"
if [[ $MODE == graceful ]]; then
  bin/k $LEAF scale deploy/publisher --replicas=0
  sleep 3
  bin/k $LEAF scale deploy/leaf-epp --replicas=0
else
  bin/k $LEAF scale deploy/publisher --replicas=0 & A=$!
  bin/k $LEAF scale deploy/leaf-epp --replicas=0 & B=$!
  wait $A $B
fi
echo "$(date +%T) killed"; bin/k gr-hub logs deploy/registrar --since=90s | tail -3
wait $LG
echo "$(date +%T) restoring"
bin/k $LEAF set env deploy/publisher DEREGISTER_ON_EXIT- >/dev/null
bin/k $LEAF scale deploy/leaf-epp --replicas=1; bin/k $LEAF scale deploy/publisher --replicas=1
bin/k $LEAF rollout status deploy/leaf-epp --timeout=180s >/dev/null
cat results/life-$MODE.out
