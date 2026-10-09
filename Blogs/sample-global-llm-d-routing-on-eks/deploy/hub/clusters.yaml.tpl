# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Rendered by the registrar (static for the first spike). One entry per leaf cluster.
# address must be an IP: the hub Envoy forwards via ORIGINAL_DST, which can't resolve names.
apiVersion: v1
kind: ConfigMap
metadata:
  name: mc-hub-clusters
data:
  clusters.yaml: |
    endpoints:
${ENTRIES}
