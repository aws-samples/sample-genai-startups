# SimpleVercelAgent

This sample shows how to bring your own [Vercel AI SDK](https://sdk.vercel.ai/docs) agent to
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/).

The agent (`VercelAgent`) uses Claude Sonnet 4.6 via Amazon Bedrock through the Vercel AI SDK's
`@ai-sdk/amazon-bedrock` provider and the `ToolLoopAgent` abstraction — the idiomatic way to build
multi-step tool-calling agents in the Vercel AI SDK. Your agent code lives in `app/VercelAgent/`
and is completely framework-native Vercel AI SDK. The only AgentCore-specific touch is the HTTP
server contract (POST `/invocations` + GET `/ping` on port 8080).

> **CLI limitation — why CDK is used directly**
>
> The AgentCore CLI (`agentcore dev` / `agentcore deploy`) currently only supports Python-based
> runtimes. Because this sample uses a Node.js container, the CLI toolchain is not available and
> we use AWS CDK L1 constructs (`CfnRuntime` from `aws-cdk-lib/aws-bedrockagentcore`) to deploy
> directly, without any dependency on `@aws/agentcore-cdk` or `agentcore-cli`.
>
> **Future:** Once `agentcore-cli` adds support for non-Python (TypeScript/Node.js) Docker
> containers, this sample will be updated to use the L3 CDK constructs from `@aws/agentcore-cdk`
> and the standard CLI workflow (`agentcore deploy` / `agentcore invoke`).

## Project Structure

```
SimpleVercelAgent/
├── agentcore/
│   ├── agentcore.json      # Agent resource specification (source of truth for deployment)
│   ├── aws-targets.json    # Deployment targets (account, region)
│   └── cdk/                # CDK infrastructure — deploy directly with cdk deploy
└── app/
    └── VercelAgent/        # Your agent code — iterate here
        ├── src/
        │   └── index.ts    # ToolLoopAgent definition + AgentCore HTTP server
        ├── package.json    # Node.js dependencies
        ├── tsconfig.json   # TypeScript configuration
        └── Dockerfile      # Container build definition
```

## Quick Start

```bash
make test      # build Docker image and run tests against the local container
make stop      # stop and remove the local test container
make deploy    # install CDK deps and deploy to AWS
make destroy   # tear down the deployed AWS stack
```

## How It Works

`src/index.ts` defines the agent using `ToolLoopAgent` — the Vercel AI SDK's high-level agent
abstraction — and wraps it in a minimal Node.js HTTP server that satisfies the AgentCore runtime
service contract.

```typescript
import { createAmazonBedrock } from "@ai-sdk/amazon-bedrock";
import { fromNodeProviderChain } from "@aws-sdk/credential-providers";
import { ToolLoopAgent, tool, zodSchema } from "ai";
import { createServer } from "node:http";
import { z } from "zod";

// Credentials come from the IAM execution role in deployed environments.
// fromNodeProviderChain() covers env vars, IAM roles, container metadata, etc.
const bedrock = createAmazonBedrock({
  region: process.env.AWS_REGION ?? "us-east-1",
  credentialProvider: fromNodeProviderChain(),
});

// Agent is defined once at startup — model, instructions, and tools together.
// ToolLoopAgent automatically handles multi-step tool call loops (default: 20 steps).
const agent = new ToolLoopAgent({
  model: bedrock("global.anthropic.claude-sonnet-4-6"),
  instructions: "You are a helpful assistant. Use tools when appropriate.",
  tools: {
    add_numbers: tool({
      description: "Return the sum of two numbers.",
      inputSchema: zodSchema(z.object({
        a: z.number().int().describe("First number."),
        b: z.number().int().describe("Second number."),
      })),
      execute: async ({ a, b }) => a + b,
    }),
  },
  experimental_telemetry: { isEnabled: true },
});

// AgentCore service contract: POST /invocations and GET /ping on port 8080.
const server = createServer(async (req, res) => {
  if (req.method === "POST" && req.url === "/invocations") {
    const payload = JSON.parse(await readBody(req));
    const result = await agent.generate({ prompt: payload.prompt ?? "" });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ response: result.text }));
  } else if (req.url === "/ping") {
    res.writeHead(200); res.end("OK");
  }
});

server.listen(8080, "0.0.0.0");
```

**Why `ToolLoopAgent` over `generateText`?**

| | `generateText()` | `ToolLoopAgent` |
|---|---|---|
| Agent definition | Inline per request | Defined once at module level |
| Multi-step control | Manual (`stopWhen`) | Built-in (default 20 steps) |
| Observability | Manual | Lifecycle callbacks (`onStepFinish`, etc.) that integrate with OTEL |
| Reusability | Copy-paste | Single instance, called with `agent.generate()` |

**Why `fromNodeProviderChain`?**

`@ai-sdk/amazon-bedrock` does not automatically use the AWS SDK credential chain — it only checks
for explicit `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables. In AgentCore,
credentials are provided via the IAM execution role (similar to ECS task roles), so
`fromNodeProviderChain()` from `@aws-sdk/credential-providers` is required to pick them up.

## Prerequisites

- **Node.js** 20.x or later
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
1. Simple prompt (no tool use) — `"What is the capital of France?"`
2. Tool use — `"What is 42 plus 58?"`
3. Multi-step tool use — `"Add 10 and 20, then add 5 to the result."`

To manually build and run the container:

```bash
cd app/VercelAgent
docker build --platform linux/arm64 -t vercel-agent .
docker run -p 8080:8080 \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e OTEL_SDK_DISABLED=true \
  vercel-agent
```

Invoke the local agent:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 42 plus 58?"}'
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
  --payload '{"prompt": "What is 42 plus 58?"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 \
  response.txt && cat response.txt
```

Run all three test cases:

```bash
# Simple prompt
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "What is the capital of France?"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 response.txt && cat response.txt

# Tool use
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "What is 42 plus 58?"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 response.txt && cat response.txt

# Multi-step tool use
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AgentRuntimeArn> \
  --payload '{"prompt": "Add 10 and 20, then add 5 to the result."}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 response.txt && cat response.txt
```

> **AWS CLI blob quirk:** The `--payload` parameter is typed as a blob. By default the AWS CLI
> treats blob inputs as base64-encoded strings, so it would try to base64-decode your JSON before
> sending — producing garbage bytes. `--cli-binary-format raw-in-base64-out` tells the CLI to send
> the value as-is (raw bytes). This flag is AWS CLI-specific; any other client (AWS SDK, `curl`,
> direct HTTP) sends `Content-Type: application/json` with raw JSON and no special handling.

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
| Runtime        | Node.js 20 (Alpine, defined in Dockerfile)      |
| Network        | `PUBLIC`                                        |
| Model Provider | `Bedrock`                                       |
| Model          | `global.anthropic.claude-sonnet-4-6`            |
| Agent API      | Vercel AI SDK `ToolLoopAgent`                   |

## Documentation

- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Vercel AI SDK — Building Agents](https://ai-sdk.dev/docs/agents/building-agents)
- [Vercel AI SDK — Amazon Bedrock Provider](https://sdk.vercel.ai/providers/ai-sdk-providers/amazon-bedrock)
- [AgentCore Runtime Service Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html)