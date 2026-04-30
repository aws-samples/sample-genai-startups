# Python 3.12 slim base with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js 20 LTS — required by Claude Code CLI, which claude-agent-sdk spawns as a subprocess
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally — claude-agent-sdk uses this as an agent subprocess
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Create user with a home directory — Claude Code CLI requires a writable home dir
RUN groupadd -r agentcore && \
    useradd -r -g agentcore -m -d /home/bedrock_agentcore bedrock_agentcore

# Install Python dependencies
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

# Copy agent source and sample files
COPY main.py ./
COPY samples/ ./samples/

# Use Bedrock IAM execution role for authentication — no ANTHROPIC_API_KEY required
ENV CLAUDE_CODE_USE_BEDROCK=1
ENV AWS_REGION=us-east-1

# AgentCore Runtime service contract: POST /invocations and GET /ping on port 8080
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
EXPOSE 8080

USER bedrock_agentcore

# opentelemetry-instrument is provided by aws-opentelemetry-distro
CMD ["opentelemetry-instrument", "python", "main.py"]
