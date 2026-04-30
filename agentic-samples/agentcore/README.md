# Amazon Bedrock AgentCore — Sample Implementations

This directory contains sample agents that demonstrate how to bring your own agent framework
to [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using different
languages, frameworks, and deployment approaches.

## Samples

| **Sample** | **Language** | **Framework** | **Tools** | **Best for** | **Deployment** | **Container** | **HTTP server contract** |
|---|---|---|---|---|---|---|---|
| [SimplePydanticAgent](pydantic-ai-agent/SimplePydanticAgent/) | Python | [Pydantic AI](https://ai.pydantic.dev/) | Custom (`add_numbers`) | Python-native agents with structured outputs | AgentCore CLI (`agentcore deploy`) | CodeZip — managed `PYTHON_3_12` runtime | `BedrockAgentCoreApp` |
| [SimpleSmolAgent](huggingface-smolagents/SimpleSmolAgent/) | Python | [HuggingFace smolagents](https://huggingface.co/docs/smolagents) | Custom (`add_numbers`) | Multi-step tool-calling with HuggingFace models | AgentCore CLI (`agentcore deploy`) | CodeZip — managed `PYTHON_3_12` runtime | `BedrockAgentCoreApp` |
| [SimpleLangChainAgent](langchain-agent/SimpleLangChainAgent/) | Python | [LangChain](https://python.langchain.com/) (`create_agent`) | Custom (`add_numbers`) | Graph-based agents with the LangChain 1.0 `create_agent` API | AgentCore CLI (`agentcore deploy`) | CodeZip — managed `PYTHON_3_12` runtime | `BedrockAgentCoreApp` |
| [SimpleVercelAgent](vercel-ai-sdk/SimpleVercelAgent/) | TypeScript / Node.js | [Vercel AI SDK](https://sdk.vercel.ai/) | Custom (`add_numbers`) | TypeScript / Node.js agents with custom tools | CDK L1 (`CfnRuntime`) | Custom Docker (Node.js 20 Alpine) | Manual `http.createServer` |
| [SimpleClaudeAgent](claude-agent-sdk/SimpleClaudeAgent/) | Python | [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/packages/agent-sdk) | Built-in (`Read`, `Bash`, `Glob`, `Grep`) | Code analysis, file inspection, command automation | CDK L1 (`CfnRuntime`) | Custom Docker (Python 3.12 + Node.js 20) | `BedrockAgentCoreApp` |
| [SimpleSpringAgent](spring-ai/SimpleSpringAgent/) | Java | [Spring AI](https://spring.io/projects/spring-ai) + [spring-ai-agentcore](https://github.com/spring-ai-community/spring-ai-agentcore) | Custom (`addNumbers` via `@Tool`) | Java / Spring Boot enterprise agents | CDK L1 (`CfnRuntime`) | Custom Docker (Corretto 21 Alpine) | `@AgentCoreInvocation` (spring-ai-agentcore) |

## Deployment Approaches

### AgentCore CLI

The [AgentCore CLI](https://github.com/aws/agentcore-cli) (`agentcore`) is an open-source
command-line tool that simplifies building and deploying agents to Amazon Bedrock AgentCore.
It handles containerization, ECR image management, IAM role provisioning, and runtime
lifecycle — letting you focus on the agent code rather than infrastructure.

Key commands:

| Command | Description |
|---------|-------------|
| `agentcore create` | Create a new AgentCore project |
| `agentcore dev` | Launch local development server |
| `agentcore deploy` | Deploy Bedrock AgentCore agent |
| `agentcore invoke` | Invoke Bedrock AgentCore endpoint |
| `agentcore status` | Retrieve details of deployed AgentCore resources |
| `agentcore add` | Add resources to your project (memory, identity, targets) |
| `agentcore remove` | Remove AgentCore resources and project |
| `agentcore package` | Package Bedrock AgentCore runtime artifacts |
| `agentcore validate` | Validate `agentcore/` config files |
| `agentcore update` | Check for and install CLI updates |

The CLI uses a `agentcore.json` configuration file as the source of truth for agent name,
build type (CodeZip or Container), network mode, and model provider. It currently supports
managed Python runtimes out of the box. Used by the Python-based samples in this repo.

### CDK L1 (`CfnRuntime`)

Direct use of the `CfnRuntime` L1 construct from `aws-cdk-lib/aws-bedrockagentcore`. Required
when a custom container image is needed (TypeScript, Java) — no managed runtime exists for
these languages in the AgentCore CLI. Gives full control over the IAM execution role, ECR
image, and runtime configuration.

## HTTP Server Contract

All samples implement the
[AgentCore Runtime Service Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html):

- `POST /invocations` — receives the agent request payload
- `GET /ping` — health check endpoint
- Both served on port `8080`

| Approach | Used by |
|----------|---------|
| `BedrockAgentCoreApp` (Python) | SimplePydanticAgent, SimpleSmolAgent, SimpleLangChainAgent, SimpleClaudeAgent |
| Manual `http.createServer` (Node.js) | SimpleVercelAgent |
| `spring-ai-agentcore-runtime-starter` (`@AgentCoreInvocation`) | SimpleSpringAgent |

## Model

All samples use `global.anthropic.claude-sonnet-4-6` via Amazon Bedrock for demonstration
purposes, but this is not a requirement.

**AgentCore is model-agnostic.** The runtime only cares about the
[service contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
(`POST /invocations` + `GET /ping` on port 8080) — it does not dictate which model your agent
calls or how. You can use any model your agent framework supports:

- Any model available on [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
  (Anthropic, Amazon Nova, Meta Llama, Mistral, Cohere, AI21, and others)
- Models from other providers (OpenAI, Google Gemini, etc.) called directly from within your
  agent container
- Self-hosted or fine-tuned models, accessed via any HTTP endpoint

To swap the model in a sample, update the model ID in the framework's configuration
(e.g., `spring.ai.bedrock.converse.chat.options.model` in `application.properties` for Spring AI,
or the `bedrock()` call in `src/index.ts` for the Vercel AI SDK). The AgentCore infrastructure
and service contract remain unchanged.

## Authentication

All samples use IAM execution roles provisioned at deploy time. The AWS SDK default credential
chain picks up credentials automatically — no `AWS_ACCESS_KEY_ID` or explicit credential
provider configuration is needed in production.