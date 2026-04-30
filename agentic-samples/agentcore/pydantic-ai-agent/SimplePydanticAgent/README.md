# SimplePydanticAgent

This sample shows how to bring your own [Pydantic AI](https://ai.pydantic.dev/) agent to
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using the
[AgentCore CLI](https://github.com/aws/agentcore-cli). The full workflow is:

```
write your agent → agentcore dev → agentcore deploy → agentcore invoke
```

The agent (`OmniAgent`) uses Claude Sonnet 4.6 via Amazon Bedrock. Your agent code lives in `app/OmniAgent/` and is
completely framework-native Pydantic AI — the only AgentCore-specific touch is a two-line wrapper that plugs it into
the runtime.

## Project Structure

```
SimplePydanticAgent/
├── agentcore/
│   ├── agentcore.json      # Agent resource specification (source of truth for deployment)
│   ├── aws-targets.json    # Deployment targets (account, region)
│   ├── .env.local          # Local credentials (gitignored)
│   └── cdk/                # CDK infrastructure (managed by the CLI — do not hand-edit)
└── app/
    └── OmniAgent/          # Your agent code — iterate here
        ├── main.py         # Pydantic AI agent + AgentCore entrypoint
        └── pyproject.toml  # Python dependencies (uv)
```

## How It Works

`main.py` is the complete agent. The only AgentCore-specific lines are the `BedrockAgentCoreApp` wrapper and the
`@app.entrypoint` decorator. Everything else is standard Pydantic AI.

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic_ai import Agent
from pydantic_ai.models.bedrock import BedrockConverseModel

app = BedrockAgentCoreApp()
agent = Agent(model, instructions="You are a helpful assistant.")

@agent.tool_plain
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b

@app.entrypoint
async def invoke(payload: dict) -> dict:
    result = await agent.run(payload.get("prompt", ""))
    return {"response": result.output}

if __name__ == "__main__":
    app.run()
```

To extend the agent: add tools with `@agent.tool` or `@agent.tool_plain`, update the instructions, or swap the model.
The runtime contract (`@app.entrypoint` shape) stays the same.

## Quick Start

```bash
make install   # install Python dependencies
make dev       # start local development server on port 8080
make test      # invoke local agent with demo prompts (separate terminal)
make deploy    # package and deploy to AWS
make invoke    # invoke the deployed agent
make status    # show deployment status
```

## Prerequisites

- **Docker Desktop** or a compatible runtime such as [Finch](https://runfinch.com/) — required by the AgentCore CLI for container operations. Finch (v1.4+) is a confirmed working alternative.
- **Node.js** 20.x or later
- **Python** 3.10+
- **uv** ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **AWS credentials** with Bedrock and AgentCore permissions
- **AgentCore CLI** — install with:

```bash
npm install -g @aws/agentcore
```

## Local Development

Install dependencies:

```bash
cd app/OmniAgent
uv sync
```

Start the local development server (runs on `0.0.0.0:8080`):

```bash
agentcore dev
```

Invoke the local agent from another terminal:

```bash
agentcore invoke "What is 42 plus 58?"
```

Or with streaming:

```bash
agentcore invoke "Tell me a story" --stream
```

Or directly with curl:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 42 plus 58?"}'
```

## Deployment

Deploy to AWS (packages the `CodeZip` artifact, provisions AgentCore Runtime via CDK):

```bash
agentcore deploy
```

Invoke the deployed agent:

```bash
agentcore invoke '{"prompt": "What is 42 plus 58?"}'
```

Check deployment status:

```bash
agentcore status
```

## Configuration

`agentcore/agentcore.json` is the source of truth for how the agent is deployed. Current configuration for OmniAgent:

| Field          | Value         |
|----------------|---------------|
| Build          | `CodeZip`     |
| Entrypoint     | `main.py`     |
| Runtime        | `PYTHON_3_12` |
| Network        | `PUBLIC`      |
| Model Provider | `Bedrock`     |

To add memory, credentials, or change the build type, edit `agentcore.json` following the type definitions in
`agentcore/.llm-context/`, then run `agentcore deploy` to apply.

## CLI Commands

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `agentcore create`   | Create a new AgentCore project                     |
| `agentcore add`      | Add resources (agent, memory, identity, target)    |
| `agentcore remove`   | Remove resources from the project                  |
| `agentcore dev`      | Launch local development server                    |
| `agentcore deploy`   | Deploy Bedrock AgentCore agent                     |
| `agentcore status`   | Retrieve details of deployed AgentCore resources   |
| `agentcore invoke`   | Invoke Bedrock AgentCore endpoint                  |
| `agentcore package`  | Package Bedrock AgentCore runtime artifacts        |
| `agentcore validate` | Validate `agentcore/` config files                 |
| `agentcore update`   | Check for and install CLI updates                  |

## Documentation

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Pydantic AI](https://ai.pydantic.dev/)
