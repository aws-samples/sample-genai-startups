# SimpleLangChainAgent

This sample shows how to bring your own [LangChain](https://python.langchain.com/) agent to
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using the
[AgentCore CLI](https://github.com/aws/agentcore-cli). The full workflow is:

```
write your agent → agentcore dev → agentcore deploy → agentcore invoke
```

The agent (`LangChainAgent`) uses Claude Sonnet 4.6 via Amazon Bedrock through
`langchain-aws`'s `ChatBedrockConverse`. The agent loop is powered by
`create_agent` from `langchain.agents` — the LangChain 1.0 unified API for
building graph-based agents backed by LangGraph. Your agent code lives in
`app/LangChainAgent/` and is completely framework-native LangChain — the only
AgentCore-specific touch is a two-line wrapper that plugs it into the runtime.

## Project Structure

```
SimpleLangChainAgent/
├── agentcore/
│   ├── agentcore.json      # Agent resource specification (source of truth for deployment)
│   ├── aws-targets.json    # Deployment targets (account, region)
│   ├── .env.local          # Local credentials (gitignored)
│   └── cdk/                # CDK infrastructure (managed by the CLI — do not hand-edit)
└── app/
    └── LangChainAgent/     # Your agent code — iterate here
        ├── main.py         # LangChain agent + AgentCore entrypoint
        └── pyproject.toml  # Python dependencies (uv)
```

## How It Works

`main.py` is the complete agent. `create_agent` from `langchain.agents` builds a graph-based
agent runtime using LangGraph under the hood. The agent moves through a graph of nodes:

```
START → model node → (tool calls?) → tools node → model node → ... → END
```

The only AgentCore-specific lines are the `BedrockAgentCoreApp` wrapper and the
`@app.entrypoint` decorator. Everything else is standard LangChain.

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrockConverse
from langchain.agents import create_agent
from langchain.tools import tool

app = BedrockAgentCoreApp()

model = ChatBedrockConverse(
    model="global.anthropic.claude-sonnet-4-6",
    region_name="us-east-1",
)

@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b

agent = create_agent(
    model,
    tools=[add_numbers],
    system_prompt="You are a helpful assistant. Use tools when appropriate.",
)

@app.entrypoint
async def invoke(payload: dict) -> dict:
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": payload.get("prompt", "")}]}
    )
    return {"response": result["messages"][-1].content}

if __name__ == "__main__":
    app.run()
```

**Why `create_agent` from `langchain.agents`?**

`create_agent` is the unified LangChain 1.0 API for building graph-based agents. It constructs
a LangGraph `StateGraph` with two nodes:

| Node | What it does |
|------|---|
| **model node** | Calls the LLM; if the model emits tool calls, routes to the tools node |
| **tools node** | Executes the requested tools and feeds results back to the model node |

The graph loops until the model produces a final response with no tool calls. `create_agent`
also supports middleware (`wrap_model_call`, `before_model`, `after_model`, `wrap_tool_call`)
and structured output via `response_format` — see the
[LangChain agents docs](https://docs.langchain.com/oss/python/langchain/agents) for details.

**Why `ChatBedrockConverse`?**

`ChatBedrockConverse` uses the Bedrock Converse API, which supports native tool calling
across all Bedrock models. The `global.anthropic.claude-sonnet-4-6` model ID uses
cross-region inference to automatically route to the best available region.

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
cd app/LangChainAgent
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
agentcore invoke "What is 42 plus 58?"
```

Check deployment status:

```bash
agentcore status
```

## Configuration

`agentcore/agentcore.json` is the source of truth for how the agent is deployed. Current
configuration for LangChainAgent:

| Field          | Value         |
|----------------|---------------|
| Build          | `CodeZip`     |
| Entrypoint     | `main.py`     |
| Runtime        | `PYTHON_3_12` |
| Network        | `PUBLIC`      |
| Model Provider | `Bedrock`     |
| Model          | `global.anthropic.claude-sonnet-4-6` (via `ChatBedrockConverse`) |
| Agent API      | LangChain `create_agent` (LangGraph under the hood) |

To add memory, credentials, or change the build type, edit `agentcore.json` following the
type definitions in `agentcore/.llm-context/`, then run `agentcore deploy` to apply.

## CLI Commands

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `agentcore dev`      | Start local development server on port 8080        |
| `agentcore invoke`   | Invoke the agent (with dev server running for local) |
| `agentcore deploy`   | Package and deploy to AWS                          |
| `agentcore status`   | Show deployment status                             |
| `agentcore add`      | Add resources (memory, identity, targets)          |
| `agentcore remove`   | Remove resources from the project                  |
| `agentcore validate` | Validate `agentcore.json` against the schema       |
| `agentcore package`  | Package agent artifacts without deploying          |

## Documentation

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [LangChain — Agents (`create_agent`)](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain — Agents concepts](https://python.langchain.com/docs/concepts/agents/)
- [langchain-aws — ChatBedrockConverse](https://python.langchain.com/docs/integrations/chat/bedrock/)
- [AgentCore Runtime Service Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
