# End-to-End LLM Customization: From Production Data to a Specialized SQL Assistant

## Workshop Overview

In this workshop you will customize a large language model (LLM) to generate accurate SQL queries from plain English questions. You will work through the full lifecycle — from preparing training data, through supervised fine-tuning (SFT), reinforcement learning from verifiable rewards (RLVR), and finally benchmarking your model against frontier models.

By the end, you will have empirical evidence that a small, specialized model trained on ~200 examples can match or exceed frontier model accuracy on domain-specific tasks.

---

## Who this is for

Data scientists, ML engineers, and solutions architects who want to see what LLM customization actually involves end to end, rather than in the abstract.

You will be comfortable if you can:

- Read Python and understand what a script is doing, even if you would not write it from scratch
- Read SQL — `SELECT`, `JOIN`, `GROUP BY`
- Find your way around the AWS Console and a JupyterLab notebook

**No prior fine-tuning experience is required.** Every training concept — LoRA, GRPO, reward functions, ablations — is explained where it first appears. You will run cells, not write training loops.

---

## Prerequisites

- **An AWS event account.** This workshop is delivered through AWS Workshop Studio and the account is provisioned for you. Bringing your own AWS account is not supported today — the labs depend on a CloudFormation stack, a seeded database, and IAM roles that Workshop Studio deploys before you start.
- **A single region.** Your event runs in one region and everything is created there. Do not switch regions in the console partway through — later labs look for resources created by earlier ones.
- **Amazon Bedrock model access.** Lab 1 uses Bedrock to generate natural language descriptions of your queries, and Lab 4 benchmarks against Claude models on Bedrock. Access is pre-configured in the event account, and Lab 0 verifies it with a test call before you reach Lab 1.

::alert[**Want to confirm your environment before you start?** None of this is required — Workshop Studio provisions all three prerequisites for you, and Lab 0 verifies each one as you run it. But if you'd like to check upfront, open a terminal in JupyterLab (**File → New → Terminal**) and run:<br/><br/>**Account and region** — `aws sts get-caller-identity` returns your 12-digit account ID, and `aws configure get region` (or `echo $AWS_REGION`) shows the single region your event runs in.<br/>**Bedrock model access** — `aws bedrock list-foundation-models --by-provider anthropic --query 'modelSummaries[].modelId'` lists the Anthropic (Claude) models available in your region. Lab 0 goes further and confirms *invoke* access with a live one-token call — a model appearing in this list can still be denied at invocation, so treat Lab 0's check as the authoritative one.]{type="info"}

---

## Cost

This workshop runs on a Workshop Studio event account, so **you incur no charges** and the account is reclaimed automatically when the event ends. There is nothing for you to shut down.

For scale, the account provisions an Aurora PostgreSQL Serverless v2 cluster, an MLflow tracking server, an `ml.t3.xlarge` JupyterLab space, three GPU training jobs (one SFT, two RLVR arms) plus evaluation jobs, and Bedrock inference for roughly 250 queries. If you adapt this workshop into your own account outside an AWS event, those resources are billed to you — estimate the charges first using the [SageMaker AI](https://aws.amazon.com/sagemaker/ai/pricing/), [Aurora](https://aws.amazon.com/rds/aurora/pricing/), and [Bedrock](https://aws.amazon.com/bedrock/pricing/) pricing pages, and see the **Cleanup** section at the end of Lab 4.

---

## What gets deployed

Before you begin, CloudFormation has already built the environment below. Lab 0 simply discovers it.

![Architecture diagram of the workshop environment. An Aurora PostgreSQL Serverless v2 cluster in a VPC holds the product_sales table and pg_stat_statements, the source of ~250 replayed queries extracted in Lab 1. Secrets Manager supplies credentials to an Evaluator Lambda (built in Lab 2) that runs generated SQL and scores it against the reference result set — serving as both the SFT evaluation metric and the RLVR reward function. SageMaker AI hosts the Domain, UserProfile, and JupyterLab space where the five notebooks run, the GPU training jobs (SFT in Lab 2, RLVR-from-SFT and RLVR-from-base ablation in Lab 3), and the MLflow tracking server that collects 11 experiments. Model weights, datasets, and access logs land in S3.](images/workshop-architecture.png)

The `product_sales` table is seeded from a **synthetic** cosmetics-sales dataset generated for this workshop — it contains no real customer, business, or personal data, and carries no third-party licensing or usage terms.

The detail worth noticing: **the database is not decoration.** `pg_stat_statements` is a PostgreSQL extension that tracks aggregated execution statistics for every SQL statement the server runs, and it is where your training data comes from. You are not training on a synthetic text-to-SQL dataset — you are training on the queries that actually ran against this schema. (Because it *aggregates* rather than logs raw text, the statements come back with their literals normalized to `$1`, `$2` placeholders — which is exactly why Lab 1 has to substitute realistic values back in.)

::alert[**A note on encryption for production adaptations.** Everything here is encrypted at rest, but with AWS-managed keys: the Aurora cluster uses the default `aws/rds` key and both S3 buckets use SSE-S3 (`AES256`). That is appropriate for a disposable workshop account. For a production deployment, prefer a customer-managed KMS key (CMK) across the stack: `KmsKeyId` on the Aurora cluster, `aws:kms` with a `KMSMasterKeyID` on the S3 buckets, `KmsKeyId` on the Secrets Manager secret, and `KmsKeyId` in the SageMaker AI Domain's default user settings. A CMK buys you scheduled key rotation, access auditing through CloudTrail, and fine-grained control over who can decrypt via the key policy — none of which the AWS-managed keys expose.]{type="info"}

::alert[**A note on participant permissions for production adaptations.** Your event role attaches two broad AWS-managed read-only policies — `AmazonSageMakerReadOnly` and `AmazonS3ReadOnlyAccess` — alongside a small scoped inline policy. Read-only *and* account-disposable makes this an acceptable convenience for a workshop: the account is provisioned per-event and reclaimed afterward, so account-wide *read* visibility carries little risk. In a persistent or shared account you would scope these down: replace `AmazonS3ReadOnlyAccess` with a custom policy whose `Resource` lists only the workshop buckets (`arn:aws:s3:::slm-weights-*` and the SageMaker default bucket), and replace `AmazonSageMakerReadOnly` with the specific `Describe*`/`List*` actions the labs actually call rather than every SageMaker read in the account. The execution role the notebooks run under (`SageMakerExecutionRole` in the stack) is already scoped this way as a worked example — see its inline policies.]{type="info"}

---

## Efficiency by design

This workshop is deliberately built to be **performance- and resource-efficient** — the architecture is not just a means to teach fine-tuning, it is itself an example of using no more compute than the task needs. That efficiency shows up in three places, and it maps onto the AWS Well-Architected Framework's **Performance Efficiency** and **Sustainability** pillars.

**Serverless data tier — Aurora Serverless v2.** The training-data database scales its capacity (in Aurora Capacity Units) to the workload instead of running a fixed, always-on instance. It is reached over the RDS Data API — HTTP, no persistent connection pool, no idle driver — so the notebook and the evaluator Lambda pay for query execution, not for holding a connection open.

**Serverless training and evaluation.** The SFT and RLVR training jobs and the `CustomScorerEvaluator` evaluations run as SageMaker AI **serverless** jobs: a GPU is provisioned when a job starts and released the moment it finishes. There is no standing training cluster to keep warm between labs — you consume GPU time only while a job is actually running.

::alert[**Right-sizing the model is the biggest efficiency lever of all.** The whole thesis of this workshop is that a **3B-parameter model, specialized on your data, can match or beat a frontier model many times its size** on a narrow task. That is a Performance Efficiency result first — a smaller model means lower inference latency, lower cost per call, and the ability to serve it on far more modest hardware. It also has a **Sustainability** dimension: a model with orders of magnitude fewer parameters draws correspondingly less energy per inference, so the specialized 3B model has a smaller compute footprint than routing the same traffic to a large general model. We won't overstate this — the training itself consumes GPU time, and the saving is realized over the serving lifetime of the model — but for a query pattern you run at volume, choosing the smallest model that clears the bar is both the efficient and the lower-impact engineering choice.]{type="info"}

Two other pillars are woven through the labs rather than the architecture:

- **Operational Excellence** — every training run and evaluation logs to a single MLflow tracking server automatically (eleven experiments by the end). That is the operational-excellence practice of instrumenting your work so decisions rest on recorded evidence, not recollection: you can compare any two runs, see whether a change helped, and reproduce a result months later. The **Reviewing Results** module at the end walks through reading these curves.
- **Reliability** — the point of the workshop is a *reliability* improvement for generative SQL. A base model writes syntactically valid SQL that quietly returns the wrong rows; by training on the queries that **actually ran against your schema** and verifying every candidate by executing it (RLVR's verifiable reward), you are directly raising how often the system produces correct, trustworthy output. Grounding the work in real query history rather than synthetic examples is what makes that reliability gain transfer to production traffic.

---

## Why LLM Customization Is Different

Training an LLM is not like training a traditional ML model.

LLMs arrive pre-trained on trillions of tokens of text. They already understand SQL syntax, database concepts, and natural language. **Your job is not to teach the model SQL — it's to show the model *your* SQL.** Your schema, your naming conventions, your business logic.

This workshop explores two complementary approaches:

| Approach | What it does | Analogy |
|----------|-------------|---------|
| **SFT** (Supervised Fine-Tuning) | Teaches the model your preferred input/output format | Showing an engineer example PRs from your repo |
| **RLVR** (Reinforcement Learning from Verifiable Rewards) | Rewards the model for producing *correct* outputs, verified by execution | Code review with automated test suites |

---

## Why SFT and RLVR, and not something else

Customization is a ladder, and you should climb it from the bottom. Each rung costs more and buys something the one below it cannot.

| Rung | What it fixes | Why it is not enough here |
|------|---------------|---------------------------|
| **Prompt engineering** | Output format, tone, obvious mistakes | Free and instant, and you should always try it first. But the schema has to go in the prompt every single time, and nothing the model learns persists between calls. Lab 4 shows what a frontier model achieves with the schema prompted in — a useful bound, and lower than you might expect. |
| **RAG** | Getting the *right* schema in front of the model | Solves retrieval, not generation. The model still writes SQL the way it always did — it just has better reference material. If it does not know your join conventions, retrieving the table definitions will not teach it. |
| **SFT** | The model's default behavior: format, schema, conventions | This is the big one for text-to-SQL, and it is where most of the gain in this workshop comes from. But SFT teaches *imitation* — it optimizes for looking like your examples, not for being correct. A query that resembles the reference but returns the wrong rows scores well during SFT training. |
| **RLVR** | Correctness itself | The model generates SQL, you *execute it*, and reward it on whether the result matches. This is the only rung that optimizes the thing you actually care about. |

### Why they are sequential, not alternatives

You cannot skip SFT and go straight to RLVR. RLVR learns by sampling many candidate answers and comparing them against each other — so it needs a model that is already producing parseable SQL some of the time. Start from a base model and nearly every rollout fails to execute, every candidate scores the same near-zero reward, there is no signal to distinguish them, and there is nothing to learn from.

You do not have to take that on faith. **Lab 3 runs it as an ablation:** the same RLVR configuration applied to the SFT checkpoint and to the raw base model, side by side. The base arm starts lower and stays lower. That result is the argument for the ordering.

### Why RLVR and not RLHF or DPO

This is the single most important idea in the workshop.

Most RL post-training needs a reward model — a separate network trained on thousands of human preference comparisons, because "is this response good?" has no programmatic answer. That is expensive, slow, and noisy.

SQL does not have that problem. **A generated query is either right or wrong, and you can find out by running it.** So the reward function can just be code: execute the model's SQL, execute the reference SQL, compare the result sets. No human labelling, no learned reward model, no preference dataset. That is what the "VR" in RLVR means — *verifiable* rewards.

This is why text-to-SQL is such a good fit for RL, and it generalizes to any domain where correctness is machine-checkable: code that must pass tests, math with a known answer, structured extraction against a schema. It generalizes far less well to open-ended tasks — summarization quality, tone, "helpfulness" — where you are back to needing human preferences.

### Is this common practice?

Yes. SFT followed by an RL stage is the standard post-training recipe for essentially every modern instruction-following model. What varies is the RL stage: verifiable rewards where correctness is checkable, human or AI preferences where it is not. This workshop uses the verifiable variant because the task allows it.

### An honest note on scale

Be prepared for the RLVR increment over SFT to be **small** in your run — on the order of a point or two of aggregate reward on ~200 training examples. That is a real result, not a broken lab, and Lab 4 says so plainly.

RLVR's value grows with the size of your dataset and the quality of your reward function. With ~200 examples and 60 gradient steps, SFT does most of the work. What you are learning here is the *mechanism* and how to evaluate whether it is paying for itself — which is exactly the judgment you would need to make on a real project.

---

## Workshop Labs

| Lab | Topic | What you do |
|---|---|---|
| Lab 0 | Environment Setup | Configure session, MLflow, and variables |
| Lab 1 | Data Preparation | Extract queries, generate training data |
| Lab 2 | Supervised Fine-Tuning (SFT) | Build evaluator, train model, evaluate |
| Lab 3 | Reinforcement Learning (RLVR) | RL training + ablation study |
| Lab 4 | Model Evaluation | Benchmark against frontier models |
| — | Reviewing Results | Read the training curves and evaluation scores in MLflow |

## Estimated Duration

| Lab | Time |
|-----|------|
| Getting Started | 10 minutes |
| Lab 0 | 5 minutes |
| Lab 1 | 15 minutes |
| Lab 2 | 45 minutes (including training job) |
| Lab 3 | 60 minutes (including training + ablation) |
| Lab 4 | 20 minutes |
| Reviewing Results | 10 minutes |
| **Total** | **~2.5 hours** |
