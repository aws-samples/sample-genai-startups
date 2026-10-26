#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Reboot the registry's Valkey node under load (a real registry outage), and watch routing.
set -euo pipefail
cd "$(dirname "$0")/.."
R=us-east-2
NODE=$(aws elasticache describe-replication-groups --region $R --replication-group-id gr-registry --query 'ReplicationGroups[0].MemberClusters[0]' --output text)
TAG=registry-outage CONCURRENCY=32 DURATION=240 MAX_TOKENS=128 loadgen/run.sh > results/registry-outage.out &
LG=$!
sleep 45
echo "reboot epoch=$(date +%s)"
aws elasticache reboot-cache-cluster --region $R --cache-cluster-id $NODE --cache-node-ids-to-reboot 0001 --query CacheCluster.CacheClusterStatus --output text
wait $LG
bin/k gr-hub logs deploy/registrar --since=6m | grep -v "^$" | tail -6
cat results/registry-outage.out
