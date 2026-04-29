# Introduction — Key Concepts

Foundational concepts behind the workshop. Read through once so the patterns in the labs make sense when you encounter them — you don't need to memorize this.

---

## What is an AI agent?

An agent is a system that combines three things: a **model**, **tools**, and a **prompt**. Unlike a simple chatbot that generates text and stops, an agent operates in a loop — it reasons about a task, takes actions using tools, observes the results, and decides what to do next. It keeps going until the task is complete.

The key distinction: a chatbot responds, an agent *acts*.

| Component | Role |
|-----------|------|
| Model | The LLM that reasons, plans, and decides which tools to use |
| Tools | Functions the agent can call — APIs, databases, file operations, other agents |
| Prompt | Instructions that define the agent's task, persona, and constraints |

## The agent loop

Every agent in this workshop runs through the same core cycle:

```
Prompt + Context
     ↓
Model reasons about the task
     ↓
Model selects tool(s) to use
     ↓
Tool executes, returns results
     ↓
Model reflects on results
     ↓
Done? → Return final answer
Not done? → Loop back to reasoning
```

Each iteration through this loop is a **cycle**. An agent that takes 5 cycles to complete a task consumed 5 rounds of model invocation — each one costing tokens and adding latency. This is why cycle count matters for cost and performance, and why you'll track it in Lab 2.

> **Why this matters for evaluation**
> A high cycle count often means the agent is struggling — retrying failed tool calls, second-guessing itself, or working with an underspecified prompt. In Lab 2, you'll instrument cycle counts per agent to identify exactly where this happens.

---

## Strands Agents SDK

[Strands Agents](https://strandsagents.com/) is an open source SDK that takes a model-driven approach to building agents. Instead of requiring developers to define complex workflows and decision trees, Strands lets the model itself decide what to do next — which tools to call, in what order, and when to stop.

A minimal agent in Strands looks like this:

```python
from strands import Agent
from strands.models.bedrock import BedrockModel

model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")

agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant.",
    tools=[my_tool],
)

result = agent("Analyze this insurance claim")
```

The SDK handles the agent loop, tool execution, and result collection. You focus on defining what the agent knows (prompt) and what it can do (tools).

### Structured outputs with Pydantic

For agents that need to produce predictable, machine-readable results — not just free-form text — Strands supports structured outputs using Pydantic models:

```python
from pydantic import BaseModel

class ClaimData(BaseModel):
    claimant_name: str
    damage_type: str
    estimated_amount: float
```

When you define an output schema, the model is constrained to return data that matches the structure. This is critical for multi-agent systems where one agent's output becomes another agent's input.

---

## Multi-agent systems

A single agent works well for focused tasks. Complex problems — like processing an insurance claim — involve multiple distinct steps that benefit from different expertise. Splitting the work across specialized agents gives you:

- **Better results** — each agent has a focused prompt optimized for one task
- **Clearer failure modes** — when something breaks, you know exactly which agent failed
- **Parallelism** — independent steps can run simultaneously, reducing total latency
- **Cost control** — conditional routing means downstream agents don't execute if upstream validation fails

### The Graph pattern

Strands supports three multi-agent patterns: Graph, Swarm, and Workflow. This workshop uses the **Graph** pattern, where you define agents as nodes and transitions as edges in a directed graph.

| Aspect | How it works |
|--------|--------------|
| Structure | You define all nodes (agents) and edges (transitions) in advance |
| Execution | The flow follows edges, with conditional logic determining the path at each node |
| State | A shared state object is passed to all agents, who can read and modify it |
| Error handling | You can define explicit error edges to route failures to specific handling nodes |

Your workshop graph:

```
Document Analysis → [Parallel] → Policy Retrieval
                               → Inspection
                 → [Join]      → Claim Summary
```

Policy Retrieval and Inspection run in parallel after Document Analysis completes, because they don't depend on each other. This reduces total latency. The graph also supports conditional routing — if Document Analysis fails validation, downstream agents won't execute, saving tokens and compute.

---

## Observability for GenAI workloads

Traditional application monitoring tracks request counts, error rates, and latency. GenAI workloads need all of that plus metrics specific to model usage:

| Metric | Why it matters |
|--------|---------------|
| Token usage (input/output) | Output tokens cost significantly more than input — a verbose agent is an expensive agent |
| Latency per agent | Identifies the bottleneck in your pipeline |
| Cycle count | High counts suggest the agent is struggling with its prompt or tools |
| Cache efficiency | Prompt caching can reduce input token costs by up to 90% — but only with properly structured prompts |
| Cost per claim | The bottom line — what does each end-to-end execution actually cost? |

In Lab 2, you'll publish these metrics to Amazon CloudWatch with agent-level dimensions so you can compare performance across your four specialists and pinpoint where to optimize.

---

## Evaluating agent output quality

Operational metrics tell you how fast and how expensive your agents are. They don't tell you whether the outputs are *correct*. For that you need evaluation — and the right strategy depends on the type of output.

### Programmatic evaluation

For structured outputs where you know the correct answer, compare agent output against ground truth using standard metrics:

| Metric | What it measures |
|--------|-----------------|
| Precision | Of the items the agent flagged, how many were correct? |
| Recall | Of the items that should have been flagged, how many did the agent catch? |
| F1 Score | The harmonic mean of Precision and Recall |

### LLM-as-Judge

For open-ended text where "correct" is subjective — like a claim summary for a human adjuster — you use another LLM to evaluate the output on defined criteria:

| Criterion | What it scores |
|-----------|---------------|
| Completeness | Does the response cover all relevant information? |
| Helpfulness | Is it actionable for the intended audience? |
| Coherence | Is it well-structured and easy to follow? |

Each criterion gets a 1–5 score. In Lab 3 you'll use Amazon Bedrock AgentCore's built-in evaluators alongside custom evaluators you define yourself.

> The most effective evaluation strategy uses both methods. Programmatic testing catches objective errors in structured data; LLM-as-Judge catches quality issues in free-form text.

---

## Amazon Bedrock AgentCore

This workshop publishes custom metrics directly to CloudWatch and implements LLM-as-Judge by hand, so you understand the fundamentals. In production, [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) provides managed services that do the same things:

- **Observability** — an OpenTelemetry-based trace/span layer over the agent lifecycle; see [Observability docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- **Evaluations** — 13 built-in evaluators plus custom ones, with on-demand and continuous (sampled production traffic) modes; see [Evaluations docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluation.html)
- **Runtime** — serverless hosting for deployed agents; see [Runtime docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)

Lab 3 touches AgentCore evaluators directly. The other pieces are good to know about but aren't required to complete the workshop.

---

Next: [Lab 1 — Multi-agent implementation](../01_Multi_agent_implementation/).
