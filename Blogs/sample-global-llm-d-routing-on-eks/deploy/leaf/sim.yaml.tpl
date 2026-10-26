# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# llm-d inference simulator standing in for vLLM. ITL/TTFT are per-cluster knobs.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sim
  labels: {app: sim}
spec:
  replicas: ${SIM_REPLICAS}
  selector:
    matchLabels: {app: sim}
  template:
    metadata:
      labels:
        app: sim
        llm-d.ai/guide: optimized-baseline
    spec:
      containers:
      - name: sim
        image: ghcr.io/llm-d/llm-d-inference-sim:v0.11.4
        args:
        - --model=Qwen/Qwen3-32B
        - --port=8000
        - --max-num-seqs=${MAX_SEQS}
        - --max-model-len=8192
        - --latency-calculator=constant
        - --time-to-first-token=${TTFT}
        - --time-to-first-token-std-dev=${TTFT_SD}
        - --inter-token-latency=${ITL}
        - --inter-token-latency-std-dev=${ITL_SD}
        - --time-factor-under-load=${LOAD_FACTOR}
        - --enable-kvcache
        - --kv-cache-size=4096
        env:
        - name: POD_IP   # --enable-kvcache refuses to start without it
          valueFrom: {fieldRef: {fieldPath: status.podIP}}
        ports:
        - {containerPort: 8000, name: http}
        readinessProbe:
          httpGet: {path: /health/ready, port: 8000}
          periodSeconds: 2
        resources:
          requests: {cpu: "100m", memory: 128Mi}
