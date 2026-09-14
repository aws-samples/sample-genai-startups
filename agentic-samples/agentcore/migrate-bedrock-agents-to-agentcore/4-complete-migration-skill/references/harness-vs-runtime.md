# Harness vs Runtime — full D1 comparison

Load this when weighing decision D1, when the user asks what Harness can or can't do,
or before recommending Runtime.

## Conceptual difference (per AWS "harness vs. Runtime")

**Harness** is a managed agent loop **powered by Strands** — you declare
model/system-prompt/tools/memory/limits as config and AWS runs the loop; most features
are a single config field (switch model or add a tool = config change, not a redeploy).

**Runtime** is a serverless hosting environment — you bring agent code (any framework
or none), wrap it with the AgentCore SDK `BedrockAgentCoreApp` entrypoint, package an
**ARM64 container to ECR**, and deploy; the loop is yours and every other primitive
(Memory, Gateway, Browser, Code Interpreter, outbound Identity) is called from your
code.

The harness actually **runs inside Runtime** (CloudTrail logs it under
`AWS::BedrockAgentCore::Runtime`). Rule of thumb: harness = configuration/no-code;
runtime = you write code (usually SDK + your framework).

## Capability grid

*On Harness, most primitives are ✅ no-code:* model selection + mid-session provider
switch (Bedrock/OpenAI/Gemini/LiteLLM), built-in shell + file_operations tools, Agent
Skills, Observability, Memory (short + long term, per-user actor scoping), Gateway,
Browser, Code Interpreter, remote MCP tools, context truncation, execution limits,
session storage / EFS / S3 Files, env vars, `InvokeAgentRuntimeCommand`, **inbound auth
IAM *and* OAuth**, outbound Identity token vault, VPC, streaming, versioning/endpoints.

*Harness ❌ (Runtime-only, requires code):* **choice of agent framework**,
**bidirectional streaming**, **non-agent-loop patterns (graph/workflow style)**, and
**hooks**.

Inline/client-side tools are 🔵 (you maintain the implementation) on both.

So graduate to Runtime specifically when you need a non-Strands framework, a graph/
workflow (non-loop) topology, bidirectional streaming, or lifecycle hooks.

## Harness escape hatches (try these before reaching for Runtime)

Custom `linux/arm64` container, shell via `InvokeAgentRuntimeCommand`, Agent Skills,
VPC, inbound JWT, persistent S3 FS — all config.

Harness limit: `bedrockModelConfig` exposes only `modelId/temperature/maxTokens/topP`.

## Migration posture

Default to Harness; graduate to Runtime only when the loop is the limitation
(tree-of-thought, framework graph semantics like LangGraph, A2A handoffs,
prompt-caching keys, extended-thinking budgets). A team can start on Harness and move
to Runtime later without rebuilding Memory, Identity, Gateway, or Observability.
