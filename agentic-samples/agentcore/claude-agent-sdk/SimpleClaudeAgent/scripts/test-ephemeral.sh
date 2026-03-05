#!/bin/bash
# Integration Test for SimpleClaudeAgent
#
# Deploys the CDK stack, runs all three test cases against the live AgentCore runtime,
# then cleans up temporary response files. The stack remains deployed.
#
# Usage:
#   chmod +x scripts/test-ephemeral.sh
#   ./scripts/test-ephemeral.sh

set -e

# ── colours ───────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDK_DIR="$SCRIPT_DIR/../agentcore/cdk"
REGION="${AWS_REGION:-us-east-1}"
ENDPOINT_URL="https://bedrock-agentcore.${REGION}.amazonaws.com"

# Derive the CloudFormation stack name from agentcore.json (matches bin/cdk.ts logic)
AGENT_NAME=$(python3 -c "
import json, pathlib
spec = json.loads(pathlib.Path('$SCRIPT_DIR/../agentcore/agentcore.json').read_text())
print(spec['name'])
")
STACK_NAME="AgentCore-${AGENT_NAME}-default"

echo "========================================="
echo " SimpleClaudeAgent — Ephemeral Test Run"
echo "========================================="
echo ""

# ── remove temp response files on exit ───────────────────────────────────────

cleanup() {
    rm -f /tmp/agentcore-response.txt
}

trap cleanup EXIT

# ── Step 1: CDK build + deploy ────────────────────────────────────────────────

echo -e "${CYAN}Step 1: Building and deploying CDK stack '${STACK_NAME}'...${NC}"
cd "$CDK_DIR"

npm install
npm run build
npx cdk deploy --require-approval never

echo -e "${GREEN}✓ Stack deployed${NC}"
echo ""

# ── Step 2: resolve AgentRuntimeArn from CloudFormation outputs ───────────────

echo -e "${CYAN}Step 2: Resolving AgentRuntimeArn from CloudFormation...${NC}"

AGENT_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" \
    --output text)

if [ -z "$AGENT_ARN" ] || [ "$AGENT_ARN" = "None" ]; then
    echo -e "${RED}✗ Could not find AgentRuntimeArn in stack outputs.${NC}"
    aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
        --query "Stacks[0].Outputs" --output table
    exit 1
fi

echo -e "${GREEN}✓ Agent Runtime ARN: ${AGENT_ARN}${NC}"
echo ""

# ── Step 3: run tests ─────────────────────────────────────────────────────────

PASS=0
FAIL=0

run_test() {
    local description="$1"
    local prompt="$2"

    echo -e "${YELLOW}Test: ${description}${NC}"
    echo "  Prompt: ${prompt}"

    set +e
    aws bedrock-agentcore invoke-agent-runtime \
        --agent-runtime-arn "$AGENT_ARN" \
        --payload "{\"prompt\": \"${prompt}\"}" \
        --cli-binary-format raw-in-base64-out \
        --endpoint-url "$ENDPOINT_URL" \
        --region "$REGION" \
        /tmp/agentcore-response.txt > /dev/null 2>&1
    status=$?
    set -e

    if [ $status -ne 0 ]; then
        echo -e "  ${RED}✗ FAIL — AWS CLI returned exit code ${status}${NC}"
        FAIL=$((FAIL + 1))
        echo ""
        return
    fi

    if python3 -c "
import sys, json
d = json.load(open('/tmp/agentcore-response.txt'))
assert 'response' in d, 'missing response key'
assert len(d['response']) > 0, 'empty response'
" 2>/dev/null; then
        echo -e "  ${GREEN}✓ PASS${NC}"
        echo "  Response:"
        python3 -m json.tool /tmp/agentcore-response.txt 2>/dev/null || cat /tmp/agentcore-response.txt
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗ FAIL — unexpected response body${NC}"
        cat /tmp/agentcore-response.txt 2>/dev/null || true
        FAIL=$((FAIL + 1))
    fi
    echo ""
}

echo -e "${CYAN}Step 3: Running tests against deployed runtime...${NC}"
echo ""

run_test "Directory structure"      "Show me the directory structure under /app"
run_test "Read and explain a file"  "Read /app/samples/calculator.py and explain what it does"
run_test "Search for TODO comments" "Search for any TODO comments in /app/samples/"

# ── Summary ───────────────────────────────────────────────────────────────────

echo "========================================="
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN} Results: ${PASS}/${PASS} passed${NC}"
else
    echo -e "${RED} Results: ${PASS} passed, ${FAIL} failed${NC}"
fi
echo "========================================="
echo ""
echo "Stack '${STACK_NAME}' remains deployed."
echo "To tear it down: cd agentcore/cdk && npx cdk destroy"
echo ""

# cleanup() removes /tmp/agentcore-response.txt automatically via EXIT trap

if [ $FAIL -gt 0 ]; then
    exit 1
fi