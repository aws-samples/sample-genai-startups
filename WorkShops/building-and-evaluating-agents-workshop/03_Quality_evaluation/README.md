# Lab 3 — Quality Evaluation

Lab 2 showed you how to measure performance and cost. This lab answers the harder question: are your agents actually producing correct results?

**Why this matters:** Speed and cost are only two parts of the equation — you need the agent output to be correct and useful. You also need different evaluation strategies depending on the type of output: exact matching for structured data, and subjective scoring for free-form text.

**Estimated time:** 40 minutes

## What you'll learn

- Creating ground truth datasets for structured outputs
- Calculating Precision, Recall, and F1 scores
- Using AgentCore's 13 built-in evaluators
- Building custom evaluators with 5-level rating scales
- Choosing the right evaluation strategy for each output type

## Two ways to evaluate

**Programmatic testing** — for structured outputs where you know the correct answer. You get Precision, Recall, and F1 scores by comparing agent output against ground truth:
- **Recall** — Does Inspection catch the fraud indicators it should?
- **Precision** — How often does it flag legitimate claims incorrectly?

**LLM-as-Judge** — for open-ended text where "correct" is subjective. You use AgentCore's evaluator model to score responses on:
- **Completeness** — Does the response cover all relevant information?
- **Helpfulness** — Is it actionable for the claims adjuster?
- **Coherence** — Is it well-structured and easy to follow?

Each criterion gets a 1–5 score.

## Which approach for which agent

Not every agent gets evaluated the same way:

| Agent | Programmatic Testing | AgentCore Evaluators |
|-------|---------------------|----------------------|
| Document Analysis | Document F1 | Completeness, Correctness |
| Inspection | Risk accuracy, Fraud F1 | Correctness |
| Claim Summary | — | Helpfulness, Coherence |

Claim Summary produces free-form text with no single "correct" answer, so it relies on LLM-as-Judge scoring rather than exact matching.

## Run it

Before opening the notebook, copy the shared files from `shared/` into this folder so the imports resolve and the AgentCore Runtime deployment cells can find the entrypoint:

```bash
cp ../shared/claims_agents.py ../shared/agentcore_entrypoint.py .
```

Then open [`lab3-quality-metrics.ipynb`](./lab3-quality-metrics.ipynb) in Jupyter.

Once you're done, follow the [cleanup section in the root README](../README.md#cleanup) to remove any resources you created.
