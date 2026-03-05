#!/bin/bash
# Local Testing Script for SimpleClaudeAgent
# Builds the Docker image and runs it locally on port 8080 for testing.
#
# Usage:
#   chmod +x scripts/run-local.sh
#   ./scripts/run-local.sh                        # uses default AWS profile
#   AWS_PROFILE=my-profile ./scripts/run-local.sh # uses a named profile

set -e

# ── colours ───────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ── configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/../app/ClaudeAgent"
IMAGE_NAME="claude-agent"
IMAGE_TAG="local-test"
CONTAINER_NAME="claude-agent-local"
PORT=8080
BASE_URL="http://localhost:${PORT}"

echo "========================================="
echo " SimpleClaudeAgent — Local Testing"
echo "========================================="
echo ""

# ── Step 1: resolve AWS credentials ──────────────────────────────────────────

echo "Step 1: Resolving AWS credentials..."

AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-$(aws configure get aws_access_key_id 2>/dev/null || echo "")}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-$(aws configure get aws_secret_access_key 2>/dev/null || echo "")}
AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-$(aws configure get aws_session_token 2>/dev/null || echo "")}
AWS_REGION=${AWS_REGION:-$(aws configure get region 2>/dev/null || echo "us-east-1")}

if [ -z "${AWS_ACCESS_KEY_ID}" ] || [ -z "${AWS_SECRET_ACCESS_KEY}" ]; then
    echo -e "${RED}✗ Could not resolve AWS credentials.${NC}"
    echo "  Run 'aws configure', or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY."
    exit 1
fi

echo -e "${GREEN}✓ Credentials resolved (region: ${AWS_REGION})${NC}"
echo ""

# ── Step 2: clean up any existing container ───────────────────────────────────

echo "Step 2: Cleaning up any existing container..."

if ${DOCKER:-docker} ps -a | grep -q "${CONTAINER_NAME}"; then
    echo "  Stopping and removing existing container '${CONTAINER_NAME}'..."
    ${DOCKER:-docker} stop "${CONTAINER_NAME}" 2>/dev/null || true
    ${DOCKER:-docker} rm   "${CONTAINER_NAME}" 2>/dev/null || true
fi

echo -e "${GREEN}✓ Clean${NC}"
echo ""

# ── Step 3: build ─────────────────────────────────────────────────────────────

echo "Step 3: Building Docker image '${IMAGE_NAME}:${IMAGE_TAG}'..."
${DOCKER:-docker} build --platform linux/arm64 -t "${IMAGE_NAME}:${IMAGE_TAG}" "${APP_DIR}"
echo -e "${GREEN}✓ Image built successfully${NC}"
echo ""

# ── Step 4: run ───────────────────────────────────────────────────────────────

echo "Step 4: Starting container on port ${PORT}..."

${DOCKER:-docker} run -d \
    --name "${CONTAINER_NAME}" \
    --platform linux/arm64 \
    -p "${PORT}:8080" \
    -e AWS_REGION="${AWS_REGION}" \
    -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
    -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
    -e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \
    -e CLAUDE_CODE_USE_BEDROCK=1 \
    -e OTEL_SDK_DISABLED=true \
    -e DOCKER_CONTAINER=1 \
    "${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${GREEN}✓ Container started${NC}"
echo ""

# ── Step 5: wait and show initial logs ───────────────────────────────────────

echo "Step 5: Waiting for server to be ready..."
sleep 5

echo ""
echo "Container status:"
${DOCKER:-docker} ps | grep "${CONTAINER_NAME}" || true

echo ""
echo "Container logs:"
echo "----------------------------------------"
${DOCKER:-docker} logs "${CONTAINER_NAME}"
echo "----------------------------------------"
echo ""

# ── Step 6: curl tests ────────────────────────────────────────────────────────

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}✓ Container is running — running tests${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

run_test() {
    local description="$1"
    local payload="$2"

    echo -e "${YELLOW}Test: ${description}${NC}"
    echo "  Payload: ${payload}"

    response=$(curl -sf -X POST "${BASE_URL}/invocations" \
        -H "Content-Type: application/json" \
        -d "${payload}" 2>&1) || {
        echo -e "  ${RED}✗ Request failed (is the container up? check: ${DOCKER:-docker} logs ${CONTAINER_NAME})${NC}"
        echo ""
        return
    }

    echo "  Response:"
    echo "${response}" | python3 -m json.tool 2>/dev/null || echo "  ${response}"
    echo ""
}

run_test "Directory structure"                  '{"prompt": "Show me the directory structure under /app"}'
run_test "Read and explain a file"              '{"prompt": "Read /app/samples/calculator.py and explain what it does"}'
run_test "Search for TODO comments"             '{"prompt": "Search for any TODO comments in /app/samples/"}'

# ── done ──────────────────────────────────────────────────────────────────────

echo "To follow live logs:  ${DOCKER:-docker} logs -f ${CONTAINER_NAME}"
echo "To stop the container:"
echo "  ${DOCKER:-docker} stop ${CONTAINER_NAME} && ${DOCKER:-docker} rm ${CONTAINER_NAME}"
echo ""
