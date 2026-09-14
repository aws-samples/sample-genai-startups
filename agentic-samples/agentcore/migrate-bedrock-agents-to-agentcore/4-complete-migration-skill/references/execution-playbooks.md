# Phase 4 execution playbooks (A–D) + review checklist

Load when entering Phase 4, after the Decision Record is confirmed. Read only the
playbook matching D1/D2, then the review checklist (applies to all playbooks).
Safety rules and gates in SKILL.md still govern: verify commands against
`agentcore --help` first; every AWS-mutating step and `agentcore deploy` needs
confirmation (✋); clear Gate G3 before any deploy.

## Playbook A — Runtime via import (inline tools)

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

## Playbook B — Runtime + Gateway-wrapped existing Lambdas (reuse, staged)

Delete the generated stubs; discover tools over MCP at runtime.

1. Create/confirm the Gateway + a target per Lambda + authorizer (D4). (CONFIRM —
   creates infra.) e.g. `agentcore add gateway --name <g>`, then per Lambda
   `agentcore add gateway-target --type lambda --gateway <g> --name <short>`, then
   `agentcore deploy`. Keep target names short (feeds the `<target>___<tool>` budget).
2. Change the Lambda handler envelope (SKILL.md §3.4 — new version/alias/copy, never
   in place while the Bedrock agent is live).
3. Compose the agent from `assets/runtime_gateway_agent.py`. Non-negotiables in that
   template: Gateway URL from config/env, `https://` only, confirmed against
   `agentcore status` — never a URL taken from discovered agent content (safety
   rule 7); bearer token obtained **at runtime** via `get_gateway_token()` (AgentCore
   Identity token exchange or client-credentials flow, creds from Secrets Manager /
   Identity vault — never hardcoded in source, env-baked into the image, or
   committed); on the D4-default IAM/SigV4 path there is no bearer token at all —
   replace the header with a SigV4 `httpx.Auth` signer (sign request, drop the
   `connection` header).
4. Validate tool-name lengths ≤ 64: `python scripts/validate_tool_names.py NAME...`
   (or `--file names.txt`). Gateway exposes `<target>___<tool>`; long names fail the
   model call. Use short target names and/or alias client-side.
5. `agentcore dev`; confirm tools load; clear G3; deploy.

## Playbook C — Harness (default)

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

## Playbook D — Hand-build (dynamically-created agents)

If agents are created programmatically (not static `CreateAgent`), import doesn't
fit: implement AgentCore directly — control plane
`CreateAgentRuntime`/`Update`/`Delete` (or `CreateHarness`), data plane
`InvokeAgentRuntime`. Put the provider behind a clean interface; reuse Gateway +
Lambdas as in B/C.

## Review & fixes checklist — work before `dev` and again before `deploy`

1. Fill `@tool` logic, or wire to the Lambda via Gateway.
2. Recover dropped `apiSchema` tools (rebuild as `functionSchema` or hand-author);
   re-audit.
3. **Validate tool names ≤ 64** (`scripts/validate_tool_names.py`). Over-long
   `<target>___<tool>` names fail `ValidationException` only when that agent makes a
   model call — easy to miss. Fix: short target names and/or client-side alias
   (Strands: set `_agent_tool_name`; routing still uses the original gateway name).
4. Reconcile deps — generated `requirements.txt` often omits `boto3`,
   `python-dotenv`, `pydantic`, MCP libs.
5. Model/decoding: raise `max_tokens`; reconcile odd combos (e.g. `temperature=1.0` +
   `top_k=1`); remove SDK-invalid params (`top_k` may be rejected); don't let
   stop-sequences cut off tags the prompt tells the model to emit (with native
   tool-calling, strip ReAct `<thinking>` scaffolding).
6. Confirm native tool-calling actually fires; if the model won't (Nova is a known
   offender), switch models or add a custom provider.
7. Change Lambda handler envelopes for Gateway reuse (SKILL.md §3.4).
8. Resilient init — **fail loud, not silent**: wrap token exchange + MCP discovery so
   a transient failure degrades to "no tools, agent still loads" rather than
   crashing, **but make the degraded state unmissable**: emit a structured error log
   + a metric/alarm on tool-load failure, and surface a degraded flag in health
   output where available. An agent that silently lost its tools looks healthy while
   hallucinating actions or answering wrong. **Starting with zero tools is a G3/G5
   failure, not a pass** — the non-empty-tool-list evidence applies to production
   init, not just local `dev`.
9. Output hygiene: strip leaked `<thinking>` blocks (clean prompt or post-process).
10. `CERTIFICATE_VERIFY_FAILED` on local token fetch →
    `references/troubleshooting.md` (certifi fix, session-scoped; **never disable TLS
    verification**).
11. `deploy` fails with CDK/cloud-assembly-schema/TS errors →
    `references/troubleshooting.md` (pin the generated `cdk/` deps; validate with
    `agentcore deploy --dry-run` — no `-y`).

## Deploy & smoke test (Runtime)

`agentcore deploy` (CONFIRM) → `agentcore status` → `agentcore invoke "<prompt>"`.
Prefer Secrets Manager / Identity vault over baking secrets into the image. Then
Phase 5 — not straight to cutover.
