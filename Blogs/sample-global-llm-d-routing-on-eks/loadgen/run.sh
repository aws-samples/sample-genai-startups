#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Run the load generator as a Job in the hub cluster and print its RESULT line.
# Usage: TAG=load-c32 CONCURRENCY=32 REQUESTS=400 loadgen/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=${TAG:-run}; JOB=lg-$(echo $TAG | tr -c 'a-z0-9-' '-' | cut -c1-40)-$(date +%s)
bin/k gr-hub create configmap loadgen-py --from-file=loadgen/loadgen.py --dry-run=client -o yaml | bin/k gr-hub apply -f - >/dev/null
cat <<EOF | bin/k gr-hub apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata: {name: $JOB}
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: lg
        image: python:3.12-slim
        command: ["sh","-c","pip install -q httpx pyyaml 2>/dev/null && python /lg/loadgen.py"]
        env:
        - {name: TAG, value: "$TAG"}
        - {name: MODEL, value: "${MODEL:-Qwen/Qwen3-32B}"}
        - {name: TARGET, value: "${TARGET:-http://hub-epp.llm-d.svc}"}
        - {name: CONCURRENCY, value: "${CONCURRENCY:-32}"}
        - {name: REQUESTS, value: "${REQUESTS:-400}"}
        - {name: MAX_TOKENS, value: "${MAX_TOKENS:-256}"}
        - {name: PROMPT_WORDS, value: "${PROMPT_WORDS:-300}"}
        - {name: DURATION, value: "${DURATION:-0}"}
        resources: {requests: {cpu: "1", memory: 512Mi}}
        volumeMounts:
        - {name: lg, mountPath: /lg}
        - {name: clusters, mountPath: /etc/clusters}
      volumes:
      - {name: lg, configMap: {name: loadgen-py}}
      - {name: clusters, configMap: {name: mc-hub-clusters}}
EOF
bin/k gr-hub wait --for=condition=complete job/$JOB --timeout=1800s >/dev/null || true
mkdir -p results; bin/k gr-hub logs job/$JOB | grep -E '^RESULT' | tee -a results/results.jsonl.raw
