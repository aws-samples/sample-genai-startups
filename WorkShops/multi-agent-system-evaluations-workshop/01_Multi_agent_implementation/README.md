# Lab 1 — Multi-Agent Implementation

Build the core of your insurance claims pipeline: four specialized agents that collaborate through a graph workflow to process claims end-to-end.

**Why this matters:** Insurance claims require different types of analysis (document review, policy lookup, fraud detection, summarization) that don't fit well in a single prompt. Splitting the work across focused agents gives you better results, clearer failure modes, and the ability to run independent steps in parallel.

**Estimated time:** 30–45 minutes

## What you'll learn

- Creating specialized agents with the Strands SDK
- Defining structured outputs using Pydantic models
- Building graph workflows with conditional edges using `GraphBuilder`
- Processing multimodal content (text + images)
- Managing dependencies between agents

## What you're building

| Agent | What it does | Input | Output |
|-------|-------------|-------|--------|
| Document Analysis | Extracts claim details from submitted documents | Text, images | Structured claim data |
| Policy Retrieval | Looks up relevant coverage and deductibles | Claim data | Policy details |
| Inspection | Identifies fraud indicators and risk factors | Claim + policy | Risk assessment |
| Claim Summary | Compiles everything into an actionable report | All agent outputs | Human-readable report |

## How the workflow connects

```
Document Analysis → [Parallel] → Policy Retrieval
                              → Inspection
                  → [Join]    → Claim Summary
```

Policy Retrieval and Inspection run in parallel after Document Analysis completes — they don't depend on each other, so running them concurrently reduces total latency. The graph structure also enables conditional routing: if Document Analysis fails validation, downstream agents won't execute, saving tokens and compute. You'll measure exactly how much this saves in Lab 2.

## Run it

Open [`lab1-multi-agent-system.ipynb`](./lab1-multi-agent-system.ipynb) in Jupyter. The notebook walks through building the multi-agent system from scratch. The final implementation is packaged as [`shared/claims_agents.py`](../shared/claims_agents.py) and reused by Labs 2 and 3.

Next: [Lab 2 — Operational metrics](../02_Operational_metrics/).
