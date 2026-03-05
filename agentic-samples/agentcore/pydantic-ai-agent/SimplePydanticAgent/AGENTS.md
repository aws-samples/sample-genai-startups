# SimplePydanticAgent — AI Coding Assistant Context

This is a **Bring Your Own Agent (BYOA)** sample. You have a Pydantic AI agent — the
[AgentCore CLI](https://github.com/aws/agentcore-cli) handles local dev, deployment, and invocation without
rewriting your agent code.

```
agentcore dev  →  agentcore deploy  →  agentcore invoke
```

## Mental Model

Your agent code is yours. The only AgentCore-specific integration in `main.py` is three things:

- `BedrockAgentCoreApp` — implements the runtime service contract (`POST /invocations` on port 8080)
- `@app.entrypoint` — registers your async handler as the invocation target
- `app.run()` — starts the server; driven by the CLI during `agentcore dev` and in the deployed runtime

Everything else — model, tools, instructions, dependencies — is standard Pydantic AI. You can develop and test it
as a normal Pydantic AI agent before touching AgentCore at all.

`agentcore/` is the deployment configuration layer. Edit `agentcore.json` to change how the agent is deployed.
The CLI reads this and manages the CDK infrastructure — do not edit `agentcore/cdk/` directly.

## Directory Structure

```
SimplePydanticAgent/
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
    └── OmniAgent/               # Your agent code — iterate here
        ├── main.py              # Pydantic AI agent + AgentCore entrypoint
        └── pyproject.toml       # Python dependencies (uv)
```

## Agent Implementation

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic_ai import Agent
from pydantic_ai.models.bedrock import BedrockConverseModel

app = BedrockAgentCoreApp()                          # AgentCore runtime wrapper
agent = Agent(model, instructions="...")             # Your Pydantic AI agent — unchanged

@agent.tool_plain                                    # Add tools as normal
def my_tool(x: int) -> int: ...

@app.entrypoint                                      # Wire to the runtime contract
async def invoke(payload: dict) -> dict:
    result = await agent.run(payload.get("prompt", ""))
    return {"response": result.output}

if __name__ == "__main__":
    app.run()
```

Rules for AI coding assistants modifying `main.py`:
- Do not replace `BedrockAgentCoreApp` — it implements the AgentCore service contract
- `@app.entrypoint` must be `async`, accept `dict`, return `dict`
- `app.run()` must stay under `if __name__ == "__main__"`
- Add tools with `@agent.tool` (gets `RunContext`) or `@agent.tool_plain` (no context)
- For per-invocation state (session ID, clients), use a `deps_type` dataclass — not module-level globals
- `BedrockConverseModel` uses the runtime IAM role in deployed environments — no API key needed

## CLI Commands

Install the CLI:

```bash
npm install -g @aws/agentcore
```

**Local development:**

```bash
agentcore dev                                    # start local server on 0.0.0.0:8080
agentcore invoke "What is 42 plus 58?"          # invoke the locally running agent (in another terminal)
agentcore invoke "Tell me a story" --stream     # invoke with streaming
```

**Deploy and invoke:**

```bash
agentcore deploy                                 # package CodeZip, provision via CDK, deploy
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
- **BuildType**: `'CodeZip'` (this project — no Dockerfile) | `'Container'` (Docker via CodeBuild)
- **RuntimeVersion**: `'PYTHON_3_10'` | `'PYTHON_3_11'` | `'PYTHON_3_12'` | `'PYTHON_3_13'`
- **NetworkMode**: `'PUBLIC'` | `'PRIVATE'`
- **MemoryStrategyType**: `'SEMANTIC'` | `'SUMMARIZATION'` | `'USER_PREFERENCE'`

Run `agentcore validate` after editing schemas.
