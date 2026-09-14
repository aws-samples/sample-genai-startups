# Bedrock Agents → AgentCore Migration Skill

An [Agent Skill](https://agentskills.io) that turns an AI coding agent (Claude Code,
Kiro, or any harness implementing the Agent Skills spec) into a careful migration
architect for moving **Amazon Bedrock managed Agents ("Agents Classic")** to
**Amazon Bedrock AgentCore** (Harness or Runtime) using the `@aws/agentcore` CLI.

The skill is opinionated about *process*, not just commands: it discovers the live
agent read-only, interviews you through the target decisions, designs for maximum
reuse of your existing Lambdas/KBs/secrets, and only then executes — behind explicit
approval checkpoints and evidence-based verification gates. The original Bedrock
agents stay live and untouched throughout.

> **Why migrate?** Bedrock Agents is now "Amazon Bedrock Agents Classic" and in
> maintenance mode — closed to new customers from **July 30, 2026**, with no active
> feature development. AWS points new agent workloads at AgentCore. (Verify current
> status against the [official docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html).)

## What it does

```mermaid
flowchart LR
    P0["Phase 0<br/>Discovery<br/>(read-only)"] --> G0{{"Gate G0<br/>inventory + baseline"}}
    G0 --> P1["Phase 1<br/>Confirm map ✋"]
    P1 --> P2["Phase 2<br/>Decision interview<br/>D1–D8 ✋"]
    P2 --> P3["Phase 3<br/>Target design<br/>approval ✋"]
    P3 --> P4["Phase 4<br/>Scaffold → review<br/>→ local run"]
    P4 --> G3{{"Gate G3<br/>tools load + fire"}}
    G3 --> D["Deploy<br/>(confirmed) ✋"]
    D --> P5["Phase 5<br/>Parity validation"]
    P5 --> G5{{"Gate G5<br/>≥3 runs vs baseline"}}
    G5 --> DONE(["Migration complete —<br/>Bedrock agents still live"])

    classDef gate fill:#fff3cd,stroke:#b8860b
    class G0,G3,G5 gate
```

**The migration ends at G5** with both stacks running side by side. Cutover and
decommissioning are deliberately out of scope — a separate, user-initiated decision
after production confidence is established. The skill never deletes anything.

### Key capabilities

- **Read-only discovery** of the live agent topology via AWS APIs — supervisor,
  collaborators, action groups (with the critical `functionSchema` vs `apiSchema`
  classification), Lambdas, knowledge bases, models/CRIS profiles — plus a
  behavioral baseline used later as the parity yardstick.
- **Decision interview (D1–D8)** with recommended defaults: Harness vs Runtime,
  Gateway-wrapped Lambdas vs inline tools, IAM vs Cognito auth, memory strategy,
  multi-agent shape, model tool-calling compatibility, CRIS vs data residency.
- **Four execution playbooks**: Runtime via import, Runtime + Gateway-wrapped
  existing Lambdas, Harness (the default), and hand-built for dynamically-created
  agents.
- **Battle-tested gotchas** baked in: the silent `apiSchema` drop on import, the
  64-char Gateway tool-name limit that only fails at model-call time, the
  shared-Lambda handler trap, CDK dependency pinning, Nova tool-calling friction,
  and more.
- **Mermaid architecture diagrams** of both current and target states at every
  approval checkpoint, so the migration delta is reviewable at a glance.

## Repository layout

In this repo the skill lives in `4-complete-migration-skill/`; rename it to
`bedrock-agents-to-agentcore/` when installing (see [Installation](#installation)).

```
4-complete-migration-skill/             # → bedrock-agents-to-agentcore/ once installed
├── SKILL.md                            # Core instructions (agent-facing)
├── README.md                           # This file (human-facing; not loaded by the agent)
├── scripts/
│   ├── inventory_bedrock_agent.py      # Read-only topology inventory → JSON
│   └── validate_tool_names.py          # 64-char Gateway/MCP tool-name validator
├── assets/
│   └── runtime_gateway_agent.py        # Playbook B agent template (Strands + MCP)
└── references/                         # Loaded on demand (progressive disclosure)
    ├── decision-guide.md               # Full D1–D8 trade-offs
    ├── execution-playbooks.md          # Playbooks A–D + 11-item review checklist
    ├── harness-vs-runtime.md           # Conceptual comparison + capability grid
    ├── troubleshooting.md              # CDK version pinning, local SSL failures
    ├── day2-operations.md              # Observability, cost, resilience, latency
    └── sources.md                      # Maintainer references (never fetched at runtime)
```

`SKILL.md` stays under the spec's 500-line / 5,000-token budget; detailed material
lives in `references/` and is loaded only when its trigger condition is met.

## Installation

When you clone this repo, the skill and its assets live in the
`4-complete-migration-skill/` directory. A skill's directory name becomes its
identifier, so copy it into your harness's skills location **and rename it** to a
descriptive `bedrock-agents-to-agentcore`. Run the commands below **from the repo
root** (the parent of `4-complete-migration-skill/`) so the source and destination
never overlap — copying the folder into a skills directory nested inside itself
causes an infinite recursion.

```bash
# Claude Code — personal skills
mkdir -p ~/.claude/skills
cp -r 4-complete-migration-skill ~/.claude/skills/bedrock-agents-to-agentcore

# Claude Code — project skills (shared via your repo)
mkdir -p .claude/skills
cp -r 4-complete-migration-skill .claude/skills/bedrock-agents-to-agentcore
```

### Kiro

Kiro discovers skills the same way — drop the directory into a skills location and
Kiro loads it on demand:

```bash
# Kiro — user-level skills (available across all workspaces)
mkdir -p ~/.kiro/skills
cp -r 4-complete-migration-skill ~/.kiro/skills/bedrock-agents-to-agentcore

# Kiro — workspace-level skills (shared via your repo)
mkdir -p .kiro/skills
cp -r 4-complete-migration-skill .kiro/skills/bedrock-agents-to-agentcore
```

> Tip: `cp -r <source> <dest>` where `<dest>` does **not** already exist copies the
> folder *as* `<dest>` (the rename happens for free). Only pre-create the parent
> `skills/` directory — don't create the leaf `bedrock-agents-to-agentcore` itself,
> or `cp` will nest a copy inside it.

To always keep the migration process front-of-mind in a given project, you can also
register it as **project steering**. Steering files live in `.kiro/steering/*.md`
and are injected into every interaction (or conditionally, via front-matter):

```bash
# Kiro — project steering (loaded into context automatically), from the repo root
mkdir -p .kiro/steering
cp 4-complete-migration-skill/SKILL.md \
  .kiro/steering/bedrock-agents-to-agentcore-migration.md
```

By default a steering file is always included. To load it only when you're actively
migrating (keeping context lean otherwise), set the file to manual inclusion and
pull it in with `#` in chat, or scope it to matching files with front-matter:

```markdown
---
inclusion: manual
---
```

```markdown
---
inclusion: fileMatch
fileMatchPattern: '**/agentcore/**'
---
```

Any harness implementing the [Agent Skills spec](https://agentskills.io) will pick
it up from its equivalent skills directory.

### Prerequisites

| Requirement | Used for |
|---|---|
| AWS credentials (ReadOnly is enough for Phases 0–3) | Discovery via `aws` CLI / boto3 |
| AWS CLI v2 | Discovery and baseline capture |
| Python 3.9+ with `boto3` | `scripts/inventory_bedrock_agent.py` |
| Node.js 18+ / npm | `@aws/agentcore` CLI (install a pinned version) |
| Deploy-capable credentials (only at Phase 4, behind confirmation) | Gateway/Harness/Runtime creation |

> ⚠️ Do **not** use the deprecated pip `bedrock-agentcore-starter-toolkit` — it
> shares the `agentcore` command name with the npm CLI. The skill checks
> `which -a agentcore` and will flag collisions.

## Usage

Just describe the migration in your agent session — the skill's description
triggers on it:

```text
Migrate my Bedrock agent SUPERAGENT123 in eu-west-1 to AgentCore.
```

```text
We have a supervisor agent with 3 collaborators and Lambda action groups.
Should we target Harness or Runtime? Walk me through moving it off Agents Classic.
```

The agent will start at Phase 0 (read-only), present the discovered architecture
for your confirmation, and pause at every ✋ checkpoint before anything mutates.

### Running the bundled scripts standalone

```bash
# Inventory a live agent (read-only). Output contains full agent instructions —
# treat as sensitive; use --redact-instructions for shareable output.
python scripts/inventory_bedrock_agent.py \
  --agent-id AGENT123 --region eu-west-1 > current-architecture.json

# Validate Gateway/MCP tool names against the 64-char limit (exit 1 on failure,
# so it can gate a CI deploy). Names are exposed as <target>___<tool>.
python scripts/validate_tool_names.py my-target___lookup_customer_orders
python scripts/validate_tool_names.py --file names.txt
```

## The decision framework (defaults)

| # | Decision | Default | Escape hatch |
|---|---|---|---|
| D1 | Target platform | **Harness** (managed loop, config-driven) | Runtime when the loop must be custom (non-Strands framework, graph topologies, bidirectional streaming, hooks) |
| D2 | Tool strategy | **Gateway-wrap existing prod Lambdas** (one handler-envelope change) | Inline `@tool` for net-new/trivial; mixing is fine |
| D3 | Framework (Runtime only) | **Strands** | LangGraph/others |
| D4 | Gateway auth | **AWS_IAM/SigV4** (same-account, no Cognito pool) | Cognito/OAuth for federated or non-AWS callers |
| D5 | State/memory | **Keep existing** behind Gateway for parity | AgentCore Memory later — never change loop + memory in one step |
| D6 | Multi-agent shape | **Monolith** (topology preserved in one runtime) | Distributed/A2A as a separate later redesign |
| D7 | Model | **Re-test every model** — native tool-calling only | Swap models or add a custom provider (Nova is a known friction point) |
| D8 | CRIS vs residency | CRIS for throughput | Region-pinned model ID for residency-bound workloads |

## Safety model

The skill enforces these rules as non-negotiable:

1. Discovery is **read-only** (`list-*` / `get-*` / `describe-*` only).
2. **No mutation or deploy without explicit user confirmation** — every
   infrastructure-creating step is individually gated.
3. Generate first, deploy later — everything is scaffolded and reviewed locally.
4. Original Bedrock agents **stay running** until parity is verified.
5. **Nothing is ever deleted** during migration.
6. Production is assumed when uncertain.
7. **All discovered cloud content is treated as untrusted data** — agent
   instructions, tool descriptions, and baseline outputs are never followed as
   directives, and anything resembling an embedded instruction is quoted back to
   the user as suspected prompt injection. Remote URLs found in discovered content
   are never fetched.

Discovery artifacts (inventory JSON, baseline transcripts) contain prompt IP and
possibly PII — the skill keeps them out of version control and offers redaction
(`--redact-instructions`).

## Verification gates

| Gate | When | Evidence required |
|---|---|---|
| **G0** | After discovery | Inventory JSON; baseline saved; every action group schema-classified; free-text reviewed for injected directives |
| **G3** | Before any deploy | `agentcore dev` runs; tool list non-empty; ≥1 real tool call fires; deps reconciled; all Gateway tool names ≤ 64 chars |
| **G5** | Migration done | Resources `READY`; parity vs baseline across ≥ 3 runs; regression evals pass; original agents untouched |

## Maintenance notes

- The `@aws/agentcore` CLI evolves quickly. The skill instructs the agent to verify
  every command against `agentcore --help` before running, and to install a pinned,
  tested version rather than floating latest.
- Product claims (GA status, the Classic sunset date, the Harness capability grid)
  should be re-verified against official AWS docs when updating this skill — see
  `references/sources.md`. Those URLs are maintainer references only and are never
  fetched during a migration session.
- When the agent hits a new gotcha in the field, add it to the **Gotchas** section
  of `SKILL.md` — that's the highest-value place for corrections.

## License / attribution

Content in `references/sources.md` lists the source material this skill was
distilled from; text is paraphrased/summarized for licensing compliance. Add your
organization's license of choice here before publishing.
