---
name: bedrock-agents-to-agentcore
description: >-
  Migrate Amazon Bedrock managed Agents to Amazon Bedrock AgentCore (Harness or
  Runtime) using the new @aws/agentcore CLI. Use when the user wants to migrate,
  move off, or modernize Bedrock managed agents; mentions "AgentCore", "Harness vs
  Runtime", "agentcore create/import", bring-your-own-agent, or reusing existing
  Lambda action groups as AgentCore tools. Discovers and maps the current Bedrock
  agent (read-only AWS CLI), runs an interactive decision interview, designs a
  best-practice target that reuses existing resources, then executes with review
  and verification gates before any deploy.
---

# Bedrock Managed Agents → AgentCore Migration

Be a careful migration architect: understand what exists, help the user choose the
right target deliberately, design it to best practice while reusing existing
resources, then execute — with the user approving the design and verified evidence
gates passing before anything is deployed. Work top-to-bottom; pause at every
checkpoint (✋).

## Scope

- **New `@aws/agentcore` CLI only** (`npm install -g @aws/agentcore`; now generally
  available — the `agentcore` GA line, e.g. v0.21+). **Do NOT use** the deprecated pip
  `bedrock-agentcore-starter-toolkit` / `agentcore import-agent`. Both share the
  `agentcore` command name — if the old pip/uv/pipx tool is installed, uninstall it to
  avoid PATH confusion (`which -a agentcore`).
- The CLI evolves quickly. Treat commands/flags here as a starting point and **verify
  against `agentcore --help` / `agentcore <subcommand> --help` and `agentcore --version`**
  before running.
- **Extensible**: discovery writes a normalized inventory; planning and execution
  read from it, so single agents, supervisor multi-agent systems, KB-backed agents,
  and Lambda/OpenAPI action groups all use the same flow.
- **Cloud is the source of truth — never assume a local project directory.** The
  source Bedrock agents may exist only as cloud resources with no local code/config.
  Do **all** discovery via AWS APIs (CLI / boto3), not by reading local files. If a
  local export happens to exist, treat it only as an unverified hint and still
  confirm against the live account.

## Mental model (keep the user oriented)

Three layers people conflate — be explicit:
- **Bedrock Agents** = managed *agent service*. AWS owns the loop; action-group +
  Lambda is the product. Hard ceiling: no prompt caching, no extended thinking,
  text-only input, sequential tools, logic scattered across IAM/Lambda/OpenAPI/config.
- **Agentic frameworks** (Strands, LangGraph, ...) = SDKs where *you* own the loop.
- **AgentCore** = managed *runtime platform* hosting agents, adding Memory, Identity,
  Gateway, Observability, Evaluations. NOT an agent, NOT a framework. A Gateway is a
  *tools* front door, not an agent.

Two migration targets:
- **Harness** — managed loop, declarative ("defaults at create, overrides at
  invocation"), low-code. **Default recommendation.**
- **Runtime (code / BYOA)** — you own the loop in a framework; agent is an HTTP server
  (`POST /invocations`, `GET /ping`). Choose only when the **loop itself must be
  custom**: tree-of-thought, framework graph semantics (LangGraph), A2A handoffs,
  prompt-caching keys, extended-thinking budgets.

> Default to Harness; graduate to Runtime only when the loop is the limitation. A team
> can start on Harness and move to Runtime later without rebuilding Memory, Identity,
> Gateway, or Observability.

## Safety rules (non-negotiable, LOW FREEDOM)

1. **Discovery is read-only** — only `list-*`/`get-*`/`describe-*`. Prefer ReadOnly /
   least-privilege credentials.
2. **No mutation or deploy without explicit user confirmation.** Creating Gateways,
   Cognito pools, IAM roles, runtimes, harnesses, and any `agentcore deploy` are gated
   on the user approving the target design (Phase 3) first.
3. **Generate first, deploy later.** Always scaffold and review before any deploy.
4. **Keep the original Bedrock agents running** until parity is verified (Phase 5).
5. **Never delete** Bedrock agents, Lambdas, tables, or other resources during
   migration. Cleanup is a separate, explicitly-approved post-cutover step.
6. **Assume production when uncertain**; never disable safeguards without confirmation.

## Verification gates (require evidence — do not skip)

Before advancing past a gate, produce the listed evidence. If a step is tempting to
skip, don't — these are the failures that bite at deploy time.

- **G0 (after discovery):** inventory JSON exists; baseline outputs saved; every
  action group classified `functionSchema` vs `apiSchema`.
- **G3 (before any deploy):** `agentcore dev` runs; **tool list is non-empty**; **at
  least one real tool call fires** on a representative prompt; dependencies reconciled
  (imports vs requirements); **on the Gateway path, all MCP tool names ≤ 64 chars**
  (validator passes — inline `@tool` import names are short and usually fine).
- **G5 (migration done):** AgentCore resources deployed + `READY`; parity diff vs
  baseline across **≥ 3 runs**; regression eval set passes; original Bedrock agents
  untouched and still live. Migration stops here — cutover/deletion is a separate,
  optional, user-initiated step.

Common rationalizations to reject: "tools probably load" (prove it — print the list);
"names look short enough" (run the validator); "one run worked" (agents are
non-deterministic; run ≥ 3).

## Artifacts to produce (offer to save into the workspace)

Current-architecture map (P0) · Migration Decision Record (P2) · Target architecture
doc (P3) · generated AgentCore project (P4) · parity report (P5).

---

# Phase 0 — Discovery (read-only)

1. **Confirm environment:** `aws sts get-caller-identity`; confirm region + profile
   (Bedrock agents are regional — wrong region = empty inventory).
2. **Re-fetch IDs (not stable — recreation changes them):**
   ```bash
   aws bedrock-agent list-agents --region "$REGION" \
     --query "agentSummaries[].{name:agentName,id:agentId,status:agentStatus}" --output table
   aws bedrock-agent list-agent-aliases --agent-id "$AGENT_ID" --region "$REGION" \
     --query "agentAliasSummaries[].{alias:agentAliasName,id:agentAliasId}" --output table
   ```
   Confirm: agent + **all collaborators `PREPARED`**; pointed at a **stable versioned
   alias** (not scratch); for multi-agent, the **SUPERVISOR** (not each sub-agent).
3. **Inventory the topology:** run `inventory_bedrock_agent.py` (Appendix A) →
   `current-architecture.json`. It walks the agent and collaborators and captures, per
   agent: model / CRIS profile, instruction, guardrails; action groups with executor
   (Lambda ARN) and **schema type** (`functionSchema` vs `apiSchema`); KBs;
   collaborators. It flags `apiSchema` groups, which **import silently drops**
   (rebuild as `functionSchema` upstream or hand-author the tool later).
   For each backing Lambda, read identity only:
   ```bash
   aws lambda get-function --function-name "$FN" --region "$REGION" \
     --query "Configuration.{name:FunctionName,runtime:Runtime,arn:FunctionArn,role:Role,timeout:Timeout,mem:MemorySize}"
   ```
4. **Capture a behavioral baseline** (the parity yardstick for Phase 5):
   ```bash
   aws bedrock-agent-runtime invoke-agent --agent-id "$AGENT_ID" --agent-alias-id "$ALIAS_ID" \
     --session-id "baseline-$(date +%s)" --input-text "<representative prompt>" --region "$REGION" /dev/stdout
   ```
5. **Model drift:** retired model snapshots fail with `resourceNotFoundException` —
   note the model ID and whether it is a CRIS profile (`us.`/`global.` prefix).

**Gate G0** before proceeding.

# Phase 1 — Confirm the architecture map  ✋

Present the discovered topology in plain language (summary + inventory). Ask the user
to confirm or correct (wrong alias, scratch agents, retired models). Do not plan on an
unconfirmed map.

# Phase 2 — Decision interview  ✋

Walk each decision using the confirmed inventory; record in the Decision Record below.

**D1 Target — Harness vs Runtime (central).** Default Harness; Runtime only when the
agent must own the loop (custom reasoning, LangGraph graph semantics, A2A handoffs,
prompt-caching keys, extended-thinking budgets). Harness escape hatches before you
reach for Runtime: custom `linux/arm64` container, shell via `InvokeAgentRuntimeCommand`,
Agent Skills, VPC, inbound JWT, persistent S3 FS — all config. Harness limit:
`bedrockModelConfig` exposes only `modelId/temperature/maxTokens/topP`.

**D2 Tool strategy — reuse Lambdas via Gateway vs inline `@tool`** (the big reuse call).
- *Gateway-wrapped Lambdas* (recommended for existing prod Lambdas): keep packages,
  IAM, CI/CD, `functionSchema` shapes; agent/harness reaches them over MCP. **One
  required change**: the Lambda handler envelope (§3.4). Caveats: Gateway isn't free
  (high volume can favor inlining); a wrapped Lambda still pays cold start + an MCP hop.
- *Inline `@tool`* (cleaner for net-new/trivial): import scaffolds stubs; you fill
  logic; Lambdas no longer invoked at runtime. Mixing both is fine.

**D3 Framework (Runtime only):** Strands (AWS-native default) vs LangGraph/others.
**D4 Gateway auth:** Cognito/OAuth (per-Gateway pool; more token mgmt) vs IAM/SigV4
(simpler for AWS-native Lambda tools, but you implement a SigV4 `httpx.Auth` signer —
sign request, drop the `connection` header). Harness `agentcore_gateway` brokers OAuth
via Identity. Pick per tool type.
**D5 State/memory:** keep existing (e.g. DynamoDB Lambda) behind Gateway for parity
(recommended first), or adopt AgentCore Memory later (don't change loop + memory in one
step).
**D6 Multi-agent shape:** monolith (default — one runtime/harness, sub-agents in-process,
topology preserved as code/config) vs distributed/A2A (independent scaling, more
complexity, Runtime-only — separate later redesign).
**D7 Model compatibility (strategic — don't skip):** AgentCore + framework delegates
tool-calling to each model's **native** structured tool-use (no Bedrock overlay).
Weak-tool-calling models stop "just working." **Nova specifically shows friction** on
Strands — not a safe default. Re-test every model. Upside: migration unlocks non-Bedrock
models (OpenAI/Gemini/etc.) with creds in Identity's vault.
**D8 CRIS vs residency:** `us.`/`global.` CRIS cuts throttling but **routes across
Regions** → can violate residency (GDPR/APPI/regulated). For residency-bound workloads
use a Region-pinned model ID (no CRIS prefix) in the contracted Region.

```
Migration Decision Record — <agent> (<region>)   Date: <>   Owner: <>
D1 Target: [ ]Harness [ ]Runtime    D2 Tools: [ ]Gateway-wrap [ ]Inline [ ]Mixed
D3 Framework: ____ (Runtime only)   D4 Auth: [ ]Cognito [ ]IAM-SigV4 (per tool type)
D5 Memory: [ ]Keep existing [ ]AgentCore Memory (later)   D6 Shape: [ ]Monolith [ ]A2A
D7 Model: current __ target __ native-tool-calling OK? Y/N  re-test: __
D8 [ ]CRIS  [ ]Region-pinned (residency)   Open risks:
```
Proceed only after the user confirms this record.

# Phase 3 — Target architecture design  ✋

Turn the Decision Record into a concrete design that reuses existing resources. Get
explicit approval before any execution.

**3.1 Resource reuse map (lead with what stays).** Lambdas → reuse behind a Gateway
target (handler envelope changes; package/IAM/runtime stay). KBs → reuse. Secrets →
keep in Secrets Manager; external provider creds → AgentCore **Identity** vault (never
in the image). Custom state store → reuse behind Gateway for parity, or AgentCore
Memory later. Model/CRIS → reuse unless retired/residency-bound. Guardrails → re-attach
(changed policies in Shadow mode first). Bedrock agent resources → **keep running**.

**3.2 Harness shape (default).** Caller → Harness (managed loop, microVM/session) with
defaults in `harness.json` + per-call overrides; bind the **existing Gateway** as a
first-class tool (no MCP client code; Identity brokers OAuth); Memory/Identity/
Observability by config; optional custom container/shell/Skills/VPC/S3 FS.

**3.3 Runtime shape (code).** Caller → Runtime (HTTP) → framework agent owning the
loop, with inline `@tool` and/or an MCP client to the Gateway, model behind a
`load_model()` seam, auto-instrumented Observability. Multi-agent monolith: supervisor
`Agent` whose tools are `invoke_<collaborator>` functions, each collaborator a full
`Agent`, in one runtime.

**3.4 Gateway + Lambda contract (the required handler change).** Input: Bedrock
`event["actionGroup"]/["apiPath"]/["parameters"]` → a **flat input map**. Output:
`{"messageVersion":"1.0","response":{...}}` wrapper → **plain JSON matching the tool's
`outputSchema`**. Package/IAM/runtime unchanged. Standardize errors as
`{"status":"error","message":"..."}` so the model doesn't retry-storm on a 200 + error
body. Verify the exact event/context shape against current Gateway-Lambda-target docs.
**⚠️ Shared-Lambda parity trap:** if the Lambda is still used by the running Bedrock
agent (which you keep live until Phase 5), do NOT change its handler in place — it
expects the Bedrock envelope and you'll break the source. Point the Gateway target at a
**new Lambda version/alias (or a copy)** carrying the Gateway envelope, and cut the old
version only after cutover.

**3.5 IAM / least privilege.** Execution role assumable by
`bedrock-agentcore.amazonaws.com`, scoped to `bedrock:InvokeModel` on **specific model
ARNs** (not `*` — also turns an unreviewed model swap into a deploy-time
`AccessDeniedException`), Gateway create/invoke, `lambda:InvokeFunction` on specific
targets, X-Ray, CloudWatch Logs. Grant **`iam:PassRole`** to the calling principal —
missing it yields a late, undescriptive **403**. Partition Memory namespaces per tenant.

**3.6 Primitives.** Keep Observability on; enable Gateway if reusing Lambdas, Memory if
adopting it; disable unused primitives to cut surface area and cost.

```
Target Architecture — <agent>   Target: <Harness|Runtime>  Framework: <Strands|...>
Reused: Lambdas(via Gateway) <+which need handler change>; KBs <>; Secrets/Identity <>; Model/CRIS <id> residency <CRIS|pinned>
New: Gateway(s)+targets <> auth <Cognito|IAM-SigV4>; exec role <name+scope incl PassRole>; Memory/other <>
Shape: <monolith|distributed>  Deploy mode: <code|container> (cold-start rationale)  Open risks:
```

# Phase 4 — Execution

Pick the playbook matching the Decision Record. **Verify commands against
`agentcore --help` first.** Scaffold → review → run locally; **clear Gate G3 before any
deploy**. Every AWS-mutating step and `agentcore deploy` is gated on confirmation (✋).

**4.0 Install/verify:** `npm install -g @aws/agentcore` then `agentcore --version` /
`agentcore --help`. Lifecycle: `create` (scaffold) ·
`dev` (local hot-reload, port 8080) · `deploy` (ship — CONFIRM) · `invoke` (test).
Notes: `create` is **local + read-only** (reads the Bedrock agent, writes local files;
it does NOT create AWS infra — `deploy` does). Use **`--dry-run`** to preview, and
**`--build CodeZip|Container`** to pick deploy mode (CodeZip = "direct code deploy",
no pre-warm pool; Container = pre-warmed per endpoint).

**Playbook A — Runtime via import (inline tools).**
```bash
agentcore create --type import --name "$NAME" \
  --agent-id "$AGENT_ID" --agent-alias-id "$ALIAS_ID" \
  --region "$REGION" --framework Strands --output-dir ./<dir> [--dry-run]
```
`--name` is REQUIRED (letter-first, alphanumeric, ≤23 chars). Generates
`app/<name>/main.py` (supervisor + `invoke_<collaborator>` tools for multi-agent),
`strands_collaborator_*` modules, `agentcore/` config, and a `cdk/` stack. Each
collaborator's `functionSchema` actions become **inline `@tool` stubs** (short names —
no 64-char issue); `apiSchema` actions yield an empty `action_group_tools = []`. Then
fill tool logic (or wire to the Lambda via Gateway, Playbook B); recover dropped
`apiSchema` tools; apply the review checklist; `agentcore dev`; clear G3; deploy.

**Playbook B — Runtime + Gateway-wrapped existing Lambdas (reuse, staged).** Delete the
generated stubs; discover tools over MCP at runtime.
1. Create/confirm the Gateway + a target per Lambda + authorizer (D4). (CONFIRM —
   creates infra.) e.g. `agentcore add gateway --name <g>`, then per Lambda
   `agentcore add gateway-target --type lambda --gateway <g> --name <short>`, then
   `agentcore deploy`. Keep target names short (feeds the `<target>___<tool>` budget).
2. Change the Lambda handler envelope (§3.4).
3. Compose the agent:
```python
from strands import Agent
from strands_tools import current_time
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

mcp_client = MCPClient(lambda: streamablehttp_client(
    GATEWAY_URL, headers={"Authorization": f"Bearer {bearer_token}"}))
with mcp_client:
    gateway_tools = mcp_client.list_tools_sync()
    agent = Agent(model=load_model(), system_prompt=SYSTEM_PROMPT,
                  tools=[current_time, *gateway_tools])
    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload, context):
        async for event in agent.stream_async(payload.get("prompt")):
            if "data" in event and isinstance(event["data"], str):
                yield event["data"]
```
4. **Validate tool-name lengths ≤ 64** (Appendix B). Gateway exposes `<target>___<tool>`;
   long names fail the model call. Use short target names and/or alias client-side.
5. `agentcore dev`; confirm tools load; clear G3; deploy.

**Playbook C — Harness (default).**
```bash
agentcore create --name "$NAME" --model-provider bedrock --model-id "$MODEL_ID" --defaults
agentcore add tool --harness "$NAME" --type agentcore_gateway --gateway "$GATEWAY_NAME"
agentcore deploy   # LOW FREEDOM: CONFIRM first. Two-phase: CDK provisions exec role +
                   # build pipeline, then CLI calls CreateHarness (no CfnHarness yet)
```
Invoke with per-call overrides:
```bash
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
agentcore invoke --harness "$NAME" --system-prompt "Current time: $NOW. <prompt>" "<user prompt>"
agentcore invoke --harness "$NAME" --model-id "$CHEAPER_MODEL" --tools agentcore_browser \
  --allowed-tools "<scoped set>" --api-key-arn "<external provider key>" "<user prompt>"
```
Stretch the managed loop without Runtime: custom container
(`agentcore add harness --container ./Dockerfile`, `linux/arm64`); shell via
`InvokeAgentRuntimeCommand`; Skills baked in or installed at session start.

**Playbook D — Hand-build (dynamically-created agents).** If agents are created
programmatically (not static `CreateAgent`), import doesn't fit: implement AgentCore
directly — control plane `CreateAgentRuntime`/`Update`/`Delete` (or `CreateHarness`),
data plane `InvokeAgentRuntime`. Put the provider behind a clean interface; reuse
Gateway + Lambdas as in B/C.

**Review & fixes — work before `dev` and again before `deploy`:**
1. Fill `@tool` logic, or wire to the Lambda via Gateway.
2. Recover dropped `apiSchema` tools (rebuild as `functionSchema` or hand-author); re-audit.
3. **Validate tool names ≤ 64** (Appendix B). Over-long `<target>___<tool>` names fail
   `ValidationException` only when that agent makes a model call — easy to miss. Fix:
   short target names and/or client-side alias (Strands: set `_agent_tool_name`; routing
   still uses the original gateway name).
4. Reconcile deps — generated `requirements.txt` often omits `boto3`, `python-dotenv`,
   `pydantic`, MCP libs.
5. Model/decoding: raise `max_tokens`; reconcile odd combos (e.g. `temperature=1.0`+
   `top_k=1`); remove SDK-invalid params (`top_k` may be rejected); don't let
   stop-sequences cut off tags the prompt tells the model to emit (with native
   tool-calling, strip ReAct `<thinking>` scaffolding).
6. Confirm native tool-calling actually fires; if the model won't (Nova is a known
   offender), switch models or add a custom provider.
7. Change Lambda handler envelopes for Gateway reuse (§3.4).
8. Resilient init: wrap token exchange + MCP discovery so a transient failure degrades
   to "no tools, agent still loads" rather than crashing.
9. Output hygiene: strip leaked `<thinking>` blocks (clean prompt or post-process).
10. Local macOS SSL: `CERTIFICATE_VERIFY_FAILED` on token fetch is local CA trust —
    `pip install certifi && export SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")`
    (also `REQUESTS_CA_BUNDLE`). Doesn't occur in the Runtime Linux container.
11. **Pin the generated `cdk/` deps — floating carets break `deploy`.** The scaffold's
    `agentcore/cdk/package.json` uses `^` ranges (`@aws/agentcore-cdk`, `aws-cdk-lib`,
    `aws-cdk`) that resolve *newer* than the installed CLI supports, failing with cryptic
    errors: TS union mismatches on `HarnessConfig.tools[].type`; CDK "Cloud assembly
    schema version … 54.0.0 … need CLI ≥ 2.1129.0"; or `Cannot find module
    '@aws-cdk/cloud-assembly-schema'` after ad-hoc up/down installs. Root cause is version
    skew, not your code. Fix: pin a self-consistent set, wipe `node_modules`+lockfile, and
    reinstall. The constraint that matters: `@aws/agentcore-cdk`'s peer pins `aws-cdk-lib`
    (e.g. older alphas → `^2.248.0` = assembly schema 53, readable by the CLI; newer alphas
    → `^2.257.0` = schema 54, *not* readable by an older CLI). Pick the newest
    `@aws/agentcore-cdk` whose peer keeps `aws-cdk-lib` at a schema your CLI reads
    (`npm view @aws/agentcore-cdk@<v> peerDependencies`), pin `aws-cdk-lib` exact, and bump
    the `aws-cdk` toolkit to match. Validate with `agentcore deploy --dry-run -y` before the
    real deploy. (Also run `npm install` in `cdk/` at least once — the scaffold ships none.)

**Deploy & smoke test (Runtime):** `agentcore deploy` (CONFIRM) → `agentcore status` →
`agentcore invoke "<prompt>"`. Prefer Secrets Manager / Identity vault over baking
secrets into the image. Then Phase 5 — not straight to cutover.

# Phase 5 — Validation (migration endpoint)  ✋

**The migration is complete when the AgentCore resources are deployed, running
alongside the still-live Bedrock agents, and validated.** Cutover and decommissioning
are **out of scope** here — they are a separate, optional, explicitly user-initiated
decision (see note below). Never delete or cut over as part of the migration.

- **Parity vs the Phase 0 baseline** on the same prompts: tools fire, state shared,
  outputs complete.
- **Run ≥ 3 times** — agents are non-deterministic; reliability is a distribution.
  Re-test every model (D7).
- **Quality gate, not just `/ping`** — keep a small regression eval set (50–200 cases)
  that grows whenever a prod bug is fixed.
- **Blue/green & shadow** — no Lambda-style aliases; split traffic in the layer in
  front (Runtime versions + endpoints). Canary 5–10%, or shadow 100% to old+new, return
  only old, diff offline.
- **Gate G5 (migration done):** AgentCore resources deployed + `READY`; parity verified
  across ≥ 3 runs; original Bedrock agents untouched and still live. **Stop here.**

**Optional, separate follow-on — cutover & decommission (NOT part of migration).**
Only if the user later explicitly asks (LOW FREEDOM): once they've run on AgentCore in
production and are confident, shift traffic, then tear down replaced agents + now-unused
Lambdas/tables and lock IAM to least privilege. Until that explicit decision, **keep
Bedrock live and delete nothing.**

# Phase 6 — Day-2 operations (optional follow-on)

- **Observability — four signals** (metrics, logs, traces, **+ evaluations** — the one
  teams skip; an agent can be available and wrong). Enable CloudWatch Transaction
  Search once per account/Region; configure Vended Logs delivery; Runtime auto-instruments
  OTel (OTLP forwards to Datadog/Langfuse/etc.). Use a structured session-ID scheme
  (`{user}_{ts}_{purpose}`). Enrich spans (token counts for billing) via Strands
  lifecycle hooks. Bedrock in-stream trace consumers need real rework (in-memory OTel
  span exporter mapping to your schema tends to work).
- **Cost levers (highest first):** model routing (small→large, ~30–60%); prompt caching
  (breakpoint after system prompt + tool defs); batch inference (~50% for non-real-time);
  sample telemetry. Idle I/O-wait inside a session still bills.
- **Resilience (layered):** adaptive retry w/ backoff (NOT for content-filter — not
  retryable); circuit breaker per dependency; fallback model routing (pre-validate
  against the eval set); CRIS + multi-Region for DR (mind residency); graceful
  degradation. Standardize tool error payloads to prevent retry storms.
- **Security:** least-privilege exec role on specific model ARNs; Guardrails Shadow →
  ENFORCE; Cedar tool-authorization is the only adversarially-robust prompt-injection
  layer; sanitize tool outputs before re-feeding the model; encode tenant in Cognito
  claim + Cedar attribute.
- **Latency / cold starts:** code deploy = lower baseline but **no pre-warm pool**;
  container = higher baseline but **per-endpoint pre-warmed instances**. Slim the
  artifact; defer/lazy-init heavy work incl. **Gateway/MCP client + token exchange**;
  **reuse session IDs** within the idle window (default 15 min); pre-warm via a strategic
  ping; a **warmup sentinel** (entrypoint returns on `{"type":"warmup"}` before any
  model/tool call). Capacity unit = **concurrent sessions**, not RPS. Use p95/p99.

---

# Appendix A — `inventory_bedrock_agent.py` (read-only inventory → JSON)

Write to `scripts/inventory_bedrock_agent.py`. Recurses collaborators and flags
`apiSchema` action groups. Read-only (boto3 `bedrock-agent` describe/list/get only).

```python
#!/usr/bin/env python3
"""Read-only inventory of a Bedrock agent (+ collaborators) -> JSON on stdout.
Flags apiSchema action groups (silently dropped by import).
Usage: inventory_bedrock_agent.py --agent-id ID [--region R] [--profile P] [--version DRAFT]
Note: the collaborator's agentId field name varies across API versions; this falls
back to emitting the raw collaborator summary so nothing is lost — verify and extend."""
import argparse, json, sys
import boto3

def client(region, profile):
    sess = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return sess.client("bedrock-agent", region_name=region)

def action_groups(c, aid, ver):
    out = []
    try:
        summaries = c.list_agent_action_groups(
            agentId=aid, agentVersion=ver).get("actionGroupSummaries", [])
    except Exception as e:
        return [{"error": f"list_agent_action_groups: {e}"}]
    for s in summaries:
        try:
            ag = c.get_agent_action_group(agentId=aid, agentVersion=ver,
                actionGroupId=s["actionGroupId"])["agentActionGroup"]
        except Exception as e:
            out.append({"name": s.get("actionGroupName"), "error": str(e)}); continue
        kind = ("apiSchema" if ag.get("apiSchema")
                else "functionSchema" if ag.get("functionSchema") else "unknown")
        out.append({"name": ag.get("actionGroupName"), "schemaType": kind,
                    "executor": ag.get("actionGroupExecutor"),
                    "droppedByImport": kind == "apiSchema"})
    return out

def collaborators(c, aid, ver):
    try:
        return c.list_agent_collaborators(
            agentId=aid, agentVersion=ver).get("agentCollaboratorSummaries", [])
    except Exception:
        return []

def collab_ref(col):
    """Resolve a collaborator summary to (agentId, aliasId). The real collaborator
    agent id is in agentDescriptor.aliasArn (.../agent-alias/<AGENT_ID>/<ALIAS_ID>) —
    NOT collaboratorId (an association id) and NOT agentId (the supervisor's id)."""
    arn = (col.get("agentDescriptor") or {}).get("aliasArn", "")
    if "agent-alias/" in arn:
        tail = arn.split("agent-alias/", 1)[1].split("/")
        if len(tail) >= 2:
            return tail[0], tail[1]
    return None, None

def dump(c, aid, ver, seen):
    if not aid or aid in seen:
        return {"agentId": aid, "note": "missing id or already captured"}
    seen.add(aid)
    try:
        agent = c.get_agent(agentId=aid)["agent"]
    except Exception as e:
        return {"agentId": aid, "error": str(e)}
    node = {"agentId": aid, "name": agent.get("agentName"),
            "status": agent.get("agentStatus"), "model": agent.get("foundationModel"),
            "instruction": agent.get("instruction"),
            "actionGroups": action_groups(c, aid, ver),
            "knowledgeBases": _safe(c, "list_agent_knowledge_bases", aid, ver,
                                    "agentKnowledgeBaseSummaries"),
            "collaborators": []}
    for col in collaborators(c, aid, ver):
        sub, alias = collab_ref(col)
        child = dump(c, sub, ver, seen) if sub else {"unresolved": col}
        child["collaboratorName"] = col.get("collaboratorName")
        child["collaboratorAliasId"] = alias
        child["collaborationInstruction"] = col.get("collaborationInstruction")
        node["collaborators"].append(child)
    return node

def _safe(c, method, aid, ver, key):
    try:
        return getattr(c, method)(agentId=aid, agentVersion=ver).get(key, [])
    except Exception as e:
        return [{"error": f"{method}: {e}"}]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True)
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--profile")
    p.add_argument("--version", default="DRAFT")
    a = p.parse_args()
    c = client(a.region, a.profile)
    inv = {"region": a.region,
           "supervisor": dump(c, a.agent_id, a.version, set())}
    json.dump(inv, sys.stdout, indent=2, default=str)
    print()
    # surface apiSchema warnings on stderr
    def warn(node):
        for ag in node.get("actionGroups", []):
            if ag.get("droppedByImport"):
                print(f"WARN apiSchema (dropped by import): "
                      f"{node.get('name')}/{ag.get('name')}", file=sys.stderr)
        for col in node.get("collaborators", []):
            if isinstance(col, dict): warn(col)
    warn(inv["supervisor"])

if __name__ == "__main__":
    main()
```

# Appendix B — `validate_tool_names.py` (flag > 64-char Gateway/MCP tool names)

Write to `scripts/validate_tool_names.py`. Exit non-zero if any name is invalid so it
can gate a deploy.

```python
#!/usr/bin/env python3
"""Validate Gateway/MCP tool names vs the 64-char Converse limit; suggest aliases.
Gateway exposes tools as '<target>___<tool>'.
Usage: validate_tool_names.py NAME [NAME ...] | --file names.txt (one per line)"""
import re, sys

LIMIT = 64
def sanitize(name):
    short = re.sub(r"[^a-zA-Z0-9_-]", "_", name.split("___")[-1])
    return short[:LIMIT] or "tool"

def load(argv):
    if argv and argv[0] == "--file":
        return [l.strip() for l in open(argv[1]) if l.strip()]
    return argv

def main(argv):
    names = load(argv)
    if not names:
        sys.exit("provide tool names or --file names.txt")
    used, bad = set(), 0
    for n in names:
        if len(n) <= LIMIT and re.fullmatch(r"[a-zA-Z0-9_-]+", n or ""):
            print(f"OK   ({len(n):>3}) {n}"); continue
        bad += 1
        alias = sanitize(n)
        while alias in used:
            alias = (alias[:LIMIT - 2] + "_" + str(len(used)))[:LIMIT]
        used.add(alias)
        print(f"FAIL ({len(n):>3}) {n}\n        -> alias: {alias} ({len(alias)} chars)")
    print(f"\n{bad} of {len(names)} need an alias (limit {LIMIT}).")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main(sys.argv[1:])
```

---

## Sources (verify against current docs; CLI is preview)
- Mahapatro, "Evolving agent development on AWS: From Bedrock Agents to AgentCore
  Harness" — https://mahadhir.substack.com/p/evolving-agent-development-on-aws
- AWS sample: github.com/aws-samples/sample-genai-startups/tree/main/agentic-samples/migrate-bedrock-agents-to-agentcore
- AgentCore docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- Harness API reference: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html
- Gateway Lambda target: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html
- Startup latency (re:Post): https://repost.aws/articles/ARCJIn3t7aRC2FxiRTV1SuCA

Content paraphrased/summarized for licensing compliance.
