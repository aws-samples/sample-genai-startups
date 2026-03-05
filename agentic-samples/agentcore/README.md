# Amazon Bedrock AgentCore — Sample Implementations

This directory contains sample agents that demonstrate how to bring your own agent framework
to [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using different
languages, frameworks, and deployment approaches.

## Samples

| | [SimplePydanticAgent](pydantic-ai-agent/SimplePydanticAgent/) | [SimpleSmolAgent](huggingface-smolagents/SimpleSmolAgent/) | [SimpleLangChainAgent](langchain-agent/SimpleLangChainAgent/) | [SimpleVercelAgent](vercel-ai-sdk/SimpleVercelAgent/) | [SimpleClaudeAgent](claude-agent-sdk/SimpleClaudeAgent/) | [SimpleSpringAgent](spring-ai/SimpleSpringAgent/) |
|---|---|---|---|---|---|---|
| **Language** | Python | Python | Python | TypeScript / Node.js | Python | Java |
| **Framework** | [Pydantic AI](https://ai.pydantic.dev/) | [HuggingFace smolagents](https://huggingface.co/docs/smolagents) | [LangChain](https://python.langchain.com/) (`create_agent`) | [Vercel AI SDK](https://sdk.vercel.ai/) | [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/packages/agent-sdk) | [Spring AI](https://spring.io/projects/spring-ai) + [spring-ai-agentcore](https://github.com/spring-ai-community/spring-ai-agentcore) |
| **Tools** | Custom (`add_numbers`) | Custom (`add_numbers`) | Custom (`add_numbers`) | Custom (`add_numbers`) | Built-in (`Read`, `Bash`, `Glob`, `Grep`) | Custom (`addNumbers` via `@Tool`) |
| **Best for** | Python-native agents with structured outputs | Multi-step tool-calling with HuggingFace models | Graph-based agents with the LangChain 1.0 `create_agent` API | TypeScript / Node.js agents with custom tools | Code analysis, file inspection, command automation | Java / Spring Boot enterprise agents |
| **Deployment** | AgentCore CLI (`agentcore deploy`) | AgentCore CLI (`agentcore deploy`) | AgentCore CLI (`agentcore deploy`) | CDK L1 (`CfnRuntime`) | CDK L1 (`CfnRuntime`) | CDK L1 (`CfnRuntime`) |
| **Container** | CodeZip — managed `PYTHON_3_12` runtime | CodeZip — managed `PYTHON_3_12` runtime | CodeZip — managed `PYTHON_3_12` runtime | Custom Docker (Node.js 20 Alpine) | Custom Docker (Python 3.12 + Node.js 20) | Custom Docker (Corretto 21 Alpine) |
| **HTTP server contract** | `BedrockAgentCoreApp` | `BedrockAgentCoreApp` | `BedrockAgentCoreApp` | Manual `http.createServer` | `BedrockAgentCoreApp` | `@AgentCoreInvocation` (spring-ai-agentcore) |
| **Auth (local testing)** | AWS profile / env vars | AWS profile / env vars | AWS profile / env vars | `fromNodeProviderChain()` | `CLAUDE_CODE_USE_BEDROCK=1` + AWS profile | AWS SDK default credential chain |
| **Auth (deployed)** | IAM execution role | IAM execution role | IAM execution role | IAM execution role | IAM execution role | IAM execution role |
| **Model** | `claude-sonnet-4-6` via Bedrock Converse | `claude-sonnet-4-6` via Bedrock Converse | `claude-sonnet-4-6` via `ChatBedrockConverse` | `claude-sonnet-4-6` via `@ai-sdk/amazon-bedrock` | `claude-sonnet-4-6` via `CLAUDE_CODE_USE_BEDROCK=1` | `claude-sonnet-4-6` via Spring AI Bedrock Converse |

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