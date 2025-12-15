#!/bin/bash
# AgentCore Observability Configuration
# Source this file to enable observability with CloudWatch integration
# Usage: source observability_env.sh

 
# Enable AgentCore Observability
export AGENT_OBSERVABILITY_ENABLED=true

# Configure AWS Distro for OpenTelemetry (ADOT)
export OTEL_PYTHON_DISTRO=aws_distro
export OTEL_PYTHON_CONFIGURATOR=aws_configurator
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_TRACES_EXPORTER=otlp

# Configure CloudWatch logging
# Replace with your actual CloudWatch log group and stream if necessary
# Identify your agent in observability data
export OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=/aws/claims-assistant,x-aws-metric-namespace=ClaimsAssistant,x-aws-log-stream=runtime-logs,x-aws-metric-namespace=bedrock-agentcore
export OTEL_RESOURCE_ATTRIBUTES=service.name=claims-assistant,aws.log.group.names=/aws/claims-assistant 
