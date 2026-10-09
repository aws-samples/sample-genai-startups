# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Real vLLM on one GPU per pod. Same pool label as the simulator, so the leaf router picks it up.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  labels: {app: vllm}
spec:
  replicas: ${VLLM_REPLICAS}
  selector:
    matchLabels: {app: vllm}
  template:
    metadata:
      labels:
        app: vllm
        llm-d.ai/guide: optimized-baseline
    spec:
      tolerations: [{key: nvidia.com/gpu, operator: Exists, effect: NoSchedule}]
      nodeSelector: {gr/accel: gpu}
      containers:
      - name: vllm
        image: vllm/vllm-openai:v0.19.1
        args:
        - --model=${MODEL}
        - --port=8000
        - --max-num-seqs=${MAX_SEQS}
        - --max-model-len=4096
        - --gpu-memory-utilization=0.90
        - --dtype=${DTYPE}
        ports: [{containerPort: 8000, name: http}]
        readinessProbe:
          httpGet: {path: /health, port: 8000}
          periodSeconds: 5
        startupProbe:
          httpGet: {path: /health, port: 8000}
          periodSeconds: 10
          failureThreshold: 90
        resources:
          limits: {nvidia.com/gpu: 1}
          requests: {cpu: "2", memory: 12Gi}
        volumeMounts: [{name: shm, mountPath: /dev/shm}]
      volumes: [{name: shm, emptyDir: {medium: Memory, sizeLimit: 2Gi}}]
