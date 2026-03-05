# Amazon Bedrock AgentCore — Sample Implementations

This directory contains sample agents that demonstrate how to bring your own agent framework
to [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using different
languages, frameworks, and deployment approaches.

## Samples

| Sample | Language | Framework | Deployment | Tools | HTTP Server Contract |
|--------|----------|-----------|------------|-------|----------------------|
| [SimplePydanticAgent](pydantic-ai-agent/SimplePydanticAgent/) | Python | [Pydantic AI](https://ai.pydantic.dev/) | AgentCore CLI | `add_numbers` | `BedrockAgentCoreApp` |
| [SimpleSmolAgent](huggingface-smolagents/SimpleSmolAgent/) | Python | [HuggingFace smolagents](https://huggingface.co/docs/smolagents) | AgentCore CLI | `add_numbers` | `BedrockAgentCoreApp` |
| [SimpleVercelAgent](vercel-ai-sdk/SimpleVercelAgent/) | TypeScript / Node.js | [Vercel AI SDK](https://sdk.vercel.ai/) | CDK L1 (`CfnRuntime`) | `add_numbers` | Manual HTTP server |
| [SimpleClaudeAgent](claude-agent-sdk/SimpleClaudeAgent/) | Python | [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/packages/agent-sdk) | CDK L1 (`CfnRuntime`) | Built-in (`Read`, `Bash`, `Glob`, `Grep`) | `BedrockAgentCoreApp` |
| [SimpleSpringAgent](spring-ai/SimpleSpringAgent/) | Java | [Spring AI](https://spring.io/projects/spring-ai) + [spring-ai-agentcore](https://github.com/spring-ai-community/spring-ai-agentcore) | CDK L1 (`CfnRuntime`) | `addNumbers` (`@Tool`) | `@AgentCoreInvocation` |

## Deployment Approaches

### AgentCore CLI

The [AgentCore CLI](https://github.com/aws/agentcore-cli) (`agentcore`) is an open-source
command-line tool that simplifies building and deploying agents to Amazon Bedrock AgentCore.
It handles containerization, ECR image management, IAM role provisioning, and runtime
lifecycle — letting you focus on the agent code rather than infrastructure.

Key commands:

| Command | Description |
|---------|-------------|
| `agentcore init` | Scaffold a new agent project |
| `agentcore dev` | Run and test your agent locally |
| `agentcore deploy` | Build, push image to ECR, and deploy to AgentCore |
| `agentcore invoke` | Invoke a deployed agent runtime |
| `agentcore delete` | Tear down a deployed runtime |

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
| `BedrockAgentCoreApp` (Python) | SimplePydanticAgent, SimpleSmolAgent, SimpleClaudeAgent |
| Manual `http.createServer` (Node.js) | SimpleVercelAgent |
| `spring-ai-agentcore-runtime-starter` (`@AgentCoreInvocation`) | SimpleSpringAgent |

## Model

All samples use `global.anthropic.claude-sonnet-4-6` via Amazon Bedrock.

## Authentication

All samples use IAM execution roles provisioned at deploy time. The AWS SDK default credential
chain picks up credentials automatically — no `AWS_ACCESS_KEY_ID` or explicit credential
provider configuration is needed in production.