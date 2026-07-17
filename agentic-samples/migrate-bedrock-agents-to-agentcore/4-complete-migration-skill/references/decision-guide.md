# Decision interview — full trade-offs for D1–D8

Load this at the start of Phase 2, before walking the decisions with the user.
For D1's full conceptual comparison and capability grid, also read
`references/harness-vs-runtime.md`.

## D1 Target — Harness vs Runtime (the central decision)

Default **Harness**; Runtime only when the agent must own the loop (custom reasoning,
LangGraph graph semantics, A2A handoffs, prompt-caching keys, extended-thinking
budgets, bidirectional streaming, lifecycle hooks, non-Strands framework). Harness
escape hatches to try first: custom `linux/arm64` container, shell via
`InvokeAgentRuntimeCommand`, Agent Skills, VPC, inbound JWT, persistent S3 FS — all
config. Harness limit: `bedrockModelConfig` exposes only
`modelId/temperature/maxTokens/topP`. Details: `references/harness-vs-runtime.md`.

## D2 Tool strategy — reuse Lambdas via Gateway vs inline `@tool` (the big reuse call)

- *Gateway-wrapped Lambdas* (recommended for existing prod Lambdas): keep packages,
  IAM, CI/CD, `functionSchema` shapes; agent/harness reaches them over MCP. **One
  required change**: the Lambda handler envelope (SKILL.md §3.4). Caveats: Gateway
  isn't free (high volume can favor inlining); a wrapped Lambda still pays cold start
  + an MCP hop.
- *Inline `@tool`* (cleaner for net-new/trivial): import scaffolds stubs; you fill
  logic; Lambdas no longer invoked at runtime. Mixing both is fine.

## D3 Framework (Runtime only)

Strands (AWS-native default) vs LangGraph/others.

## D4 Gateway auth

**Prefer AWS_IAM/SigV4 for AWS-native Lambda tools reached by a same-account
Harness** — it is simpler and drops the Cognito pool entirely. The CLI supports IAM
end-to-end: gateway `--authorizer-type AWS_IAM` + harness tool `--outbound-auth
awsIam` (the default), so no SigV4 signer code is needed on the Harness path. Use
Cognito/OAuth (per-Gateway pool; more token mgmt) when you need federated/external
identities or non-AWS callers; `agentcore_gateway` brokers that OAuth via Identity.
On the Runtime/BYOA path you own the client, so IAM means implementing a SigV4
`httpx.Auth` signer (sign request, drop the `connection` header). Pick per tool type.

## D5 State/memory

Keep existing (e.g. DynamoDB Lambda) behind Gateway for parity (recommended first),
or adopt AgentCore Memory later — don't change loop + memory in one step.

## D6 Multi-agent shape

Monolith (default — one runtime/harness, sub-agents in-process, topology preserved as
code/config) vs distributed/A2A (independent scaling, more complexity, Runtime-only —
separate later redesign).

## D7 Model compatibility (strategic — don't skip)

AgentCore + framework delegates tool-calling to each model's **native** structured
tool-use (no Bedrock overlay). Weak-tool-calling models stop "just working." **Nova
specifically shows friction** on Strands — not a safe default. Re-test every model.
Upside: migration unlocks non-Bedrock models (OpenAI/Gemini/etc.) with creds in
Identity's vault.

## D8 CRIS vs residency

`us.`/`global.` CRIS cuts throttling but **routes across Regions** → can violate
residency (GDPR/APPI/regulated). For residency-bound workloads use a Region-pinned
model ID (no CRIS prefix) in the contracted Region.
