# SimpleClaudeAgent

This sample shows how to bring your own [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)
agent to [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/).

The agent (`ClaudeAgent`) uses the Python `claude-agent-sdk` — the same tools, agent loop, and
context management that power **Claude Code**. Instead of you defining business-logic tools, Claude
autonomously uses built-in tools (`Read`, `Bash`, `Glob`, `Grep`) to complete tasks.
The `BedrockAgentCoreApp` wrapper from `bedrock-agentcore` handles the HTTP server contract
(`POST /invocations` + `GET /ping` on port 8080).

> **CLI limitation — why CDK is used directly**
>
> The AgentCore CLI (`agentcore dev` / `agentcore deploy`) supports Python `CodeZip` runtimes.
> However, the Claude Agent SDK Python package works by **spawning Claude Code CLI as a subprocess**
> (Claude Code is a Node.js tool), so the container requires both Python and Node.js. This rules out
> the managed `PYTHON_3_12` CodeZip runtime and requires a custom `Container` build. We therefore
> use AWS CDK L1 constructs (`CfnRuntime` from `aws-cdk-lib/aws-bedrockagentcore`) to deploy
> directly.
>
> **Future:** Once `agentcore-cli` adds support for custom container images (or once
> `claude-agent-sdk` no longer requires a Node.js subprocess), this sample will be updated to use
> the L3 CDK constructs from `@aws/agentcore-cdk` and the standard CLI workflow.

## Project Structure

```
SimpleClaudeAgent/
├── agentcore/
│   ├── agentcore.json      # Agent resource specification (source of truth for deployment)
│   ├── aws-targets.json    # Deployment targets (account, region)
│   └── cdk/                # CDK infrastructure — deploy directly with cdk deploy
└── app/
    └── ClaudeAgent/        # Your agent code — iterate here
        ├── main.py         # BedrockAgentCoreApp + claude-agent-sdk query() loop
        ├── pyproject.toml  # Python dependencies
        ├── samples/        # Sample source files for demo prompts
        └── Dockerfile      # Python 3.12 + Node.js 20 + Claude Code CLI
```

## Quick Start

```bash
make test         # build Docker image and run tests against the local container
make stop         # stop and remove the local test container
make deploy       # install CDK deps and deploy to AWS
make deploy-test  # deploy to AWS and run integration tests against the live runtime
make destroy      # tear down the deployed AWS stack
```

## How It Works

`main.py` defines the agent using `query()` from `claude-agent-sdk` and exposes it via
`BedrockAgentCoreApp` — the idiomatic way to build AgentCore-compatible Python agents.

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from claude_agent_sdk import query, ClaudeAgentOptions

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload: dict) -> dict:
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",   # non-interactive — no approval prompts
    )

    final_result = ""
    async for message in query(prompt=payload.get("prompt", ""), options=options):
        if hasattr(message, "result"):
            final_result = message.result or ""

    return {"response": final_result}

if __name__ == "__main__":
    app.run()
```

**How `query()` works:**

`query()` is an async generator that yields typed messages as Claude works through the task.
Each message represents a step in the agent loop (tool calls, tool results, assistant text).
The final `ResultMessage` carries the `.result` field with Claude's completed response.

**Why a custom container (not CodeZip)?**

`claude-agent-sdk` works by spawning the `claude` CLI as a subprocess. Claude Code CLI is a
Node.js application, so the container must have both Python _and_ Node.js installed. The managed
`PYTHON_3_12` CodeZip runtime only provides Python, so a custom Dockerfile is required.

**Why `CLAUDE_CODE_USE_BEDROCK=1`?**

Setting this environment variable tells Claude Code CLI to use Amazon Bedrock for inference
instead of the Anthropic API. Credentials are provided automatically via the IAM execution role
(container metadata endpoint), so no `ANTHROPIC_API_KEY` is needed.

## Prerequisites

- **Docker Desktop** or a compatible runtime such as [Finch](https://runfinch.com/) — required for container builds and local testing. Finch (v1.4+) is a confirmed working alternative — use `make test DOCKER=finch`.
- **AWS CDK CLI** — install with `npm install -g aws-cdk`
- **AWS credentials** with permissions for Bedrock, ECR, IAM, and CloudFormation

## Local Testing

The `scripts/run-local.sh` script builds the Docker image and runs all three test cases against the
local container using your current AWS profile credentials:

```bash
chmod +x scripts/run-local.sh
./scripts/run-local.sh
```

To use a specific AWS profile:

```bash
AWS_PROFILE=my-profile ./scripts/run-local.sh
```

The script runs three tests automatically:
1. Directory structure — `"Show me the directory structure under /app"`
2. File explanation — `"Read /app/samples/calculator.py and explain what it does"`
3. Code search — `"Search for any TODO comments in /app/samples/"`

To manually build and run the container:

```bash
cd app/ClaudeAgent
docker build --platform linux/arm64 -t claude-agent .
docker run -p 8080:8080 \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e CLAUDE_CODE_USE_BEDROCK=1 \
  -e OTEL_SDK_DISABLED=true \
  claude-agent
```

Invoke the local agent:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Show me the directory structure under /app"}'
```

## Deployment

### 1. Configure your AWS account

Edit `agentcore/aws-targets.json` and replace `<YOUR_AWS_ACCOUNT_ID>` with your 12-digit AWS
account ID.

### 2. Bootstrap CDK (first time only)

```bash
cd agentcore/cdk
npm install
npm run build
npx cdk bootstrap
```

### 3. Deploy the stack

```bash
npx cdk deploy
```

This builds the Docker image, pushes it to ECR, creates the IAM execution role with the required
Bedrock + ECR + CloudWatch permissions, and provisions the AgentCore Runtime. Note the
`AgentRuntimeId` and `AgentRuntimeArn` output values when the deployment completes.

### 4. Test the deployed agent

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "Show me the directory structure under /app"}' \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 \
  response.txt && cat response.txt
```

Run all three test cases:

```bash
# Directory structure
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "Show me the directory structure under /app"}' \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 response.txt && cat response.txt

# Read and explain a file
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "Read /app/samples/calculator.py and explain what it does"}' \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 response.txt && cat response.txt

# Search for TODO comments
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "Search for any TODO comments in /app/samples/"}' \
  --cli-binary-format raw-in-base64-out \
  --endpoint-url https://bedrock-agentcore.us-east-1.amazonaws.com \
  --region us-east-1 response.txt && cat response.txt
```

> **AWS CLI endpoint and blob quirks:**
> - `--endpoint-url` is required because the AWS CLI resolves `bedrock-agentcore invoke-agent-runtime`
>   to a different internal endpoint by default. Specifying the data-plane URL explicitly fixes a 404.
> - `--cli-binary-format raw-in-base64-out` is needed because `--payload` is typed as a blob and the
>   CLI would otherwise base64-decode the value before sending. Any other client (AWS SDK, `curl`,
>   direct HTTP) sends `Content-Type: application/json` with no special handling.

### 5. Tear down

```bash
npx cdk destroy
```

## Configuration

`agentcore/agentcore.json` is the source of truth for how the agent is deployed. Current
configuration:

| Field          | Value                                           |
|----------------|-------------------------------------------------|
| Build          | `Container`                                     |
| Runtime        | Python 3.12 + Node.js 20 (defined in Dockerfile)|
| Network        | `PUBLIC`                                        |
| Model Provider | `Bedrock`                                       |
| Model          | `global.anthropic.claude-sonnet-4-6` (via `CLAUDE_CODE_USE_BEDROCK=1`) |
| Agent API      | Claude Agent SDK `query()`                      |

## Documentation

- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Claude Agent SDK — Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK — Python](https://platform.claude.com/docs/en/agent-sdk/python)
- [AgentCore Runtime Service Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
