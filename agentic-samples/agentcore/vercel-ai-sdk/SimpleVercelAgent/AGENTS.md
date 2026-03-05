# SimpleVercelAgent — AI Coding Assistant Context

This is a **Bring Your Own Agent (BYOA)** sample. You have a Vercel AI SDK agent — the
[AgentCore CLI](https://github.com/aws/agentcore-cli) handles local dev, deployment, and invocation
without rewriting your agent code.

```
agentcore dev  →  agentcore deploy  →  agentcore invoke
```

## Mental Model

Your agent code is yours. The only AgentCore-specific integration is an HTTP server that implements
the runtime service contract:

- `POST /invocations` — receives `{"prompt": "..."}`, returns `{"response": "..."}`
- `GET /ping` — health check

The server runs on port 8080. Everything else — model, tools, system prompt — is standard Vercel AI
SDK. You can develop and test it as a normal Node.js app before touching AgentCore at all.

`agentcore/` is the deployment configuration layer. Edit `agentcore.json` to change how the agent
is deployed. The CLI reads this and manages the CDK infrastructure — do not edit `agentcore/cdk/`
directly.

## Directory Structure

```
SimpleVercelAgent/
├── AGENTS.md                    # This file
├── README.md                    # Developer-facing documentation
├── agentcore/                   # Deployment config — managed by the CLI
│   ├── agentcore.json           # Agent resource spec (source of truth)
│   ├── aws-targets.json         # Deployment targets (account, region)
│   ├── .env.local               # Local credentials (gitignored)
│   ├── .llm-context/            # TypeScript type definitions for schema validation
│   │   ├── agentcore.ts         # AgentCoreProjectSpec types
│   │   └── aws-targets.ts       # AWSDeploymentTarget types
│   └── cdk/                     # Generated CDK project (do not hand-edit)
└── app/
    └── VercelAgent/             # Your agent code — iterate here
        ├── src/
        │   └── index.ts         # Vercel AI SDK agent + HTTP server (AgentCore entrypoint)
        ├── package.json         # Node.js dependencies
        ├── tsconfig.json        # TypeScript configuration
        └── Dockerfile           # Container build (Node.js 20 Alpine, multi-stage)
```

## Agent Implementation

```typescript
import { createAmazonBedrock } from "@ai-sdk/amazon-bedrock";
import { generateText, tool } from "ai";
import { createServer } from "node:http";
import { z } from "zod";

const bedrock = createAmazonBedrock({ region: "us-east-1" });

// POST /invocations handler — the AgentCore service contract
async function invoke(payload: { prompt?: string }) {
  const result = await generateText({
    model: bedrock("global.anthropic.claude-sonnet-4-6"),
    maxSteps: 10,                              // enables multi-turn tool call loops
    system: "You are a helpful assistant. Use tools when appropriate.",
    prompt: payload.prompt ?? "",
    tools: {
      add_numbers: tool({
        description: "Return the sum of two numbers.",
        parameters: z.object({
          a: z.number().int().describe("First number."),
          b: z.number().int().describe("Second number."),
        }),
        execute: async ({ a, b }) => a + b,    // executes locally; result fed back to model
      }),
    },
  });
  return { response: result.text };
}
```

Rules for AI coding assistants modifying `src/index.ts`:
- The server MUST listen on `0.0.0.0:8080`
- `POST /invocations` MUST accept a JSON body and return a JSON response
- `generateText` with `maxSteps > 1` handles multi-turn tool calling automatically — do not
  implement a manual loop
- `@ai-sdk/amazon-bedrock` uses the runtime IAM role in deployed environments — no API key
  or credential injection needed; do not hardcode credentials
- Add tools by adding entries to the `tools` object; each tool needs a `description`,
  `parameters` (Zod schema), and an `execute` function
- To change the model: update the model ID string in `bedrock("...")`; use cross-region
  inference profiles (e.g. `global.anthropic.claude-sonnet-4-6`) for on-demand throughput
- The Dockerfile uses a multi-stage build (builder → production); update it if you add native
  dependencies that require build tools

## CLI Commands

Install the CLI:

```bash
npm install -g @aws/agentcore
```

**Local development:**

```bash
agentcore dev                                    # build and run container on 0.0.0.0:8080
agentcore invoke "What is 42 plus 58?"          # invoke the locally running agent (in another terminal)
```

**Deploy and invoke:**

```bash
agentcore deploy                                 # build image, provision via CDK, deploy
agentcore status                                 # check deployment state
agentcore invoke '{"prompt": "Hello"}'          # invoke the deployed agent
```

**Manage resources:**

```bash
agentcore add                                    # add memory, identity, or targets
agentcore remove                                 # remove resources from the project
agentcore deploy                                 # always re-deploy after add or remove
```

**Validate and package:**

```bash
agentcore validate                               # validate agentcore.json against the schema
agentcore package                                # package artifacts without deploying
```

## Schema Reference

Edit `agentcore/agentcore.json` to change deployment config. Type definitions are in `agentcore/.llm-context/`.

| JSON Config          | Schema File                     | Root Type               |
|----------------------|---------------------------------|-------------------------|
| `agentcore.json`     | `.llm-context/agentcore.ts`     | `AgentCoreProjectSpec`  |
| `aws-targets.json`   | `.llm-context/aws-targets.ts`   | `AWSDeploymentTarget[]` |

Key enum values:
- **BuildType**: `'CodeZip'` (Python, no Dockerfile) | `'Container'` (Docker via CodeBuild) ← this project
- **NetworkMode**: `'PUBLIC'` | `'PRIVATE'`
- **MemoryStrategyType**: `'SEMANTIC'` | `'SUMMARIZATION'` | `'USER_PREFERENCE'`

Run `agentcore validate` after editing schemas.
