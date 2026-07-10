# Bedrock Agents → AgentCore Migration Skill

An agent skill that turns "migrate my Bedrock agent to AgentCore" into a careful,
reviewable, evidence-gated workflow. It lives in [`SKILL.md`](./SKILL.md) and is
designed to be loaded by an AI coding assistant (Kiro, Claude, Codex etc.) so the
assistant behaves like a disciplined migration architect instead of improvising.

## What it does

The skill drives a migration from **Amazon Bedrock managed Agents** to **Amazon
Bedrock AgentCore** (Harness or Runtime) using the new `@aws/agentcore` CLI. It walks
the assistant through six phases, pausing for your approval (✋) and requiring proof at
each checkpoint:

1. **Discovery (read-only)** — inventories the live agent, its collaborators, action
   groups, Lambdas, knowledge bases, and models directly from AWS APIs, and captures a
   behavioral baseline. Includes a ready-to-run `inventory_bedrock_agent.py` script
   (Appendix A).
2. **Confirm the architecture map** — you verify the discovered topology before any
   planning happens.
3. **Decision interview** — an eight-question interview (Harness vs Runtime, tool reuse
   strategy, framework, Gateway auth, memory, multi-agent shape, model compatibility,
   CRIS vs data residency) captured in a Migration Decision Record.
4. **Target architecture design** — turns the decisions into a concrete design that
   *reuses* your existing Lambdas, KBs, secrets, and models, with an explicit resource
   reuse map and least-privilege IAM.
5. **Execution** — four playbooks (Runtime-via-import, Runtime + Gateway-wrapped
   Lambdas, Harness, and hand-build) with scaffold → review → local test → deploy, plus
   a `validate_tool_names.py` script (Appendix B) that catches the 64-char MCP tool-name
   limit before it bites.
6. **Validation & Day-2 ops** — parity testing against the baseline across ≥ 3 runs,
   then optional observability, cost, resilience, and security guidance.

## Why use it

Bedrock-to-AgentCore migrations are easy to get wrong in expensive ways: `apiSchema`
action groups get silently dropped on import, over-long Gateway tool names fail only at
model-call time, shared Lambdas break the still-live source agent if you edit them in
place, CRIS model IDs can quietly violate data residency, and "it worked once" hides
the non-determinism that shows up in production. This skill encodes those hard-won
lessons as guardrails so you don't rediscover them at deploy time.

Concretely, it gives you:

- **Safety by default** — discovery is strictly read-only, nothing is mutated or
  deployed without explicit confirmation, and the original Bedrock agents stay running
  until parity is verified. Nothing is deleted as part of the migration.
- **Evidence gates, not vibes** — you can't advance until the proof exists (inventory
  saved, tools actually load and fire, tool names validated, parity confirmed across
  multiple runs).
- **Maximum reuse** — the design leads with what stays (Lambdas, KBs, secrets, models)
  rather than rebuilding from scratch.
- **A clear mental model** — it keeps the distinction between Bedrock Agents, agentic
  frameworks, and AgentCore straight, and defaults to Harness while explaining exactly
  when Runtime is worth the extra ownership.

## How to use it

1. Point your AI assistant at [`SKILL.md`](./SKILL.md) (reference it in chat or load it
   as a skill/steering file).
2. Have ReadOnly or least-privilege AWS credentials configured for the region your
   Bedrock agents live in, plus the CLI: `npm install -g @aws/agentcore`.
3. Ask the assistant to migrate your agent. It will start with read-only discovery and
   pause for your input at each ✋ checkpoint.

> The `@aws/agentcore` CLI evolves quickly. The skill treats its commands as a starting
> point and verifies against `agentcore --help` and `agentcore --version` before
> running anything.

## Contents

- [`SKILL.md`](./SKILL.md) — the full skill: scope, safety rules, verification gates,
  the six-phase workflow, four execution playbooks, and two appendix scripts
  (`inventory_bedrock_agent.py`, `validate_tool_names.py`).

## Related

This is step 4 in the broader
[migrate-bedrock-agents-to-agentcore](../) sample. See `1-bedrock-agents` for the
source managed-agent example and `2-agentcore` for a generated AgentCore project.
