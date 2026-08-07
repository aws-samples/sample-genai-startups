---
title: "Lab 2: Supervised Fine-Tuning (SFT)"
weight: 40
---

# Lab 2: Supervised Fine-Tuning (SFT)

## What you will learn

- How to build an execution-based evaluator that verifies SQL against a live database
- How LoRA (Low-Rank Adaptation) enables efficient fine-tuning with small datasets
- How to evaluate a fine-tuned model against the base model for direct comparison
- How SageMaker AI's `CustomScorerEvaluator` orchestrates model evaluation pipelines

---

## Get started

1. In the JupyterLab file browser, open **`02-supervised-fine-tuning.ipynb`**.

2. Run all cells in order. The notebook is divided into three parts:

### Part 1: Create the Evaluator (~5 minutes)

The first section writes, packages, and deploys a Lambda function that:
- Takes a model's generated SQL and a reference SQL
- Executes both against the Aurora database
- Computes execution success, exact match, and F1 metrics

This same Lambda is reused as the RLVR reward function in Lab 3.

**What success looks like.** The deploy cell prints a confirmation, and the verification cell that follows waits for the function to become active and prints its details:

```
Created Lambda function: workshop_evaluator
Function ARN: arn:aws:lambda:us-east-1:123456789012:function:workshop_evaluator

Evaluator Lambda deployed successfully.
  Function name: workshop_evaluator
  Function ARN:  arn:aws:lambda:us-east-1:123456789012:function:workshop_evaluator
  State:         Active
  Runtime:       python3.12

Ready to register as a SageMaker AI Evaluator (next cell).
```

`State: Active` is the signal Part 1 succeeded — the function is deployed and invokable. (Re-running the deploy cell is safe: it prints `already exists — updating code and configuration` instead of creating a second function.) If the cell errors, check the **Lambda console** for the `workshop_evaluator` function and its **CloudWatch Logs** for the failure — a packaging or permissions problem shows up there.

### Part 2: Train with SFT (~20 minutes)

The training cell (`trainer.train()`) launches a SageMaker AI serverless training job. Key configuration:
- **Model**: Llama 3.2 3B Instruct
- **Method**: LoRA (trains ~1% of parameters)
- **Learning rate**: 1e-5
- **Epochs**: 8

The cell blocks until training completes. Monitor progress in the cell output or under **SageMaker > Training > Training Jobs** in the AWS Console.

**What success looks like.** The cell streams job logs, then ends with the job reaching a completed state — something like:

```
...
Training job status: InProgress
Training job status: InProgress
Training job status: Completed
Training complete. Model registered as version 1 in package group 'sft-model'.
```

The training loss printed in the logs should fall over the epochs (roughly ~1.5 early down to ~0.3–0.5 by epoch 8 — your exact numbers will differ). If the final status is `Failed` rather than `Completed`, open the job in **SageMaker > Training > Training Jobs** and read the failure reason there; nothing downstream will work until this shows `Completed`.

### Part 3: Evaluate (~15 minutes)

Two evaluation jobs run sequentially:
1. Against the **validation set** (held-out queries)
2. Against the **combined set** (full production distribution)

Both evaluate the fine-tuned model AND the base model (`evaluate_base_model=True`), giving a direct before/after comparison in MLflow.

Each evaluation cell blocks until the pipeline completes.

**What success looks like.** Each evaluation cell ends when its pipeline reaches a succeeded state, and the notebook prints the scores it logged to MLflow — for the validation set, roughly:

```
Evaluation complete: sft-eval-validation
  Llama 3.2 3B (base)   exec_success ~0.96   result_f1 ~0.20   aggregate_reward ~0.43
  Llama 3.2 3B (SFT)    exec_success ~0.99   result_f1 ~0.41   aggregate_reward ~0.58
```

These are reference values — **your numbers will differ** (your dataset and split are your own, and the split is small). The signal that the step *succeeded* is that it printed a base row and an SFT row for the experiment; the signal that fine-tuning *worked* is that the SFT `result_f1` and `aggregate_reward` are clearly higher than the base row. If the cell errors or no rows print, the evaluation did not complete — check **SageMaker > Processing > Processing jobs** for the failure. A fuller reading of these numbers is in the **Reviewing Results** module.

---

## MLflow experiments created

| Experiment | Content |
|-----------|---------|
| `sft-training` | Training loss curves |
| `sft-eval-validation` | Model scores on held-out queries |
| `sft-eval-combined` | Model scores on full query set |

To view these, open the **MLflow** tile in SageMaker Studio's left sidebar under *Applications*, or go to **SageMaker AI > MLflow** in the AWS Console. The last cell of the notebook also prints a direct link.

The **Reviewing Results** module at the end of the workshop walks through what to look for in each experiment.

