#!/bin/bash
# Pre-tool-use hook: restrict AWS API calls to pricing-related services only
# Allowed services: pricing, ce (Cost Explorer), sts (identity verification)

TOOL_INPUT="$1"

if echo "$TOOL_INPUT" | grep -q "service_name"; then
  SERVICE=$(echo "$TOOL_INPUT" | grep -oP '"service_name"\s*:\s*"\K[^"]+')

  if [[ ! "$SERVICE" =~ ^(pricing|ce|sts)$ ]]; then
    echo "BLOCKED: Service '$SERVICE' is not allowed. This agent can only access: pricing, ce, sts"
    exit 1
  fi
fi

exit 0
