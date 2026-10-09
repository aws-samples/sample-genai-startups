# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Leaf publisher: heartbeats this cluster's ITL record into the hub registry (Valkey).
apiVersion: v1
kind: Service
metadata: {name: sim-pods}
spec:
  clusterIP: None          # headless: DNS returns every model-server pod IP
  selector: {llm-d.ai/guide: optimized-baseline}
  ports: [{name: http, port: 8000}]
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: publisher}
spec:
  replicas: 1
  selector: {matchLabels: {app: publisher}}
  template:
    metadata: {labels: {app: publisher}}
    spec:
      terminationGracePeriodSeconds: 10
      containers:
      - name: publisher
        image: python:3.12-slim
        command: ["sh","-c","pip install -q httpx redis 2>/dev/null && exec python -u /app/publisher.py"]
        env:
        - {name: CLUSTER, value: "${CLUSTER}"}
        - {name: REGION, value: "${REGION}"}
        - {name: REDIS_HOST, value: "${REDIS_HOST}"}
        - {name: GATEWAY_HOST, value: "${GATEWAY_HOST}"}
        - {name: MAX_SEQS, value: "${MAX_SEQS}"}
        readinessProbe:   # old pod is stopped only after the new one has published
          exec: {command: ["test", "-f", "/tmp/ready"]}
          periodSeconds: 1
        resources: {requests: {cpu: 50m, memory: 128Mi}}
        volumeMounts: [{name: app, mountPath: /app}]
      volumes: [{name: app, configMap: {name: publisher-py}}]
