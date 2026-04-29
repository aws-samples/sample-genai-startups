# Lab 2 — Operational Metrics

Your agents from Lab 1 work, but right now you have no visibility into how they perform. In this lab you'll add observability so you can track what each agent costs, how long it takes, and where to optimize.

**Why this matters:** Tokens get expensive fast — a verbose agent or a poorly structured prompt can quietly burn through your budget. Without metrics, you can't fix what you can't see.

**Estimated time:** 30 minutes

## What you'll learn

- Extracting token usage and latency metrics from graph execution
- Calculating cost estimates using Claude Haiku 4.5 pricing
- Publishing custom metrics to CloudWatch with agent-level dimensions
- Building dashboard widgets for operational visibility
- Integrating native Bedrock service health metrics

## What you're building

A CloudWatch dashboard that answers these questions at a glance:

| Widget | Question it answers |
|--------|---------------------|
| Token Usage | Which agent consumes the most tokens? |
| Latency | Which agent is the bottleneck? |
| Cache Efficiency | Are you benefiting from prompt caching? |
| Cost Tracking | What does each claim cost to process? |
| Cycle Count | Are your prompts causing unnecessary agent loops? |

> **GenAI cost reality**
> - Cache reads can save up to 90% of input token cost — but only with properly structured prompts
> - High cycle counts suggest your prompts need refinement

By publishing metrics with agent-level dimensions you can compare performance across your four specialists and pinpoint exactly where to focus optimization. The metrics you instrument here feed directly into Lab 3, where you'll pair operational data with quality scores to make informed trade-off decisions.

## Run it

Before opening the notebook, copy the multi-agent implementation from `shared/` into this folder so the imports resolve:

```bash
cp ../shared/claims_agents.py .
```

Then open [`lab2-operational-metrics.ipynb`](./lab2-operational-metrics.ipynb) in Jupyter.

Next: [Lab 3 — Quality evaluation](../03_Quality_evaluation/).
