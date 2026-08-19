# End-to-End LLM Customization: From Production Data to a Specialized SQL Assistant

An AWS workshop that walks through the full lifecycle of customizing a large language model to generate accurate SQL from plain-English questions — extracting training data from a real production query history, supervised fine-tuning (SFT), reinforcement learning from verifiable rewards (RLVR), and benchmarking against frontier models.

By the end you have empirical evidence that a small (3B-parameter) model, specialized on ~200 examples of your own SQL, can match or beat a frontier model many times its size on that narrow task.

This repository is the source for an AWS Workshop Studio event, republished here so you can read the labs on GitHub and — if you want — deploy the environment into your own AWS account.

For the full workshop introduction, motivation, and architecture diagram, see [`index.en.md`](./index.en.md).

---

## Who this is for

Data scientists, ML engineers, and solutions architects who want to see what LLM customization actually involves end to end. You should be comfortable reading Python and SQL and navigating the AWS Console; no prior fine-tuning experience is required.

## What's in the box

| Module | Folder | What you do |
|---|---|---|
| Getting Started | [`0 Getting Started/`](./0%20Getting%20Started/) | Access the AWS account, open SageMaker Studio, launch JupyterLab |
| Lab 0 — Environment Setup | [`1 Environment Setup/`](./1%20Environment%20Setup/) | Configure session, MLflow, and variables |
| Lab 1 — Data Preparation | [`2 Data Preparation/`](./2%20Data%20Preparation/) | Extract queries from `pg_stat_statements`, generate training data |
| Lab 2 — Supervised Fine-Tuning | [`3 Supervised Fine-Tuning/`](./3%20Supervised%20Fine-Tuning/) | Build evaluator, train the SFT model, evaluate |
| Lab 3 — RLVR Training | [`4 RLVR Training/`](./4%20RLVR%20Training/) | RL training with verifiable rewards + ablation study |
| Lab 4 — Model Evaluation | [`5 Model Evaluation/`](./5%20Model%20Evaluation/) | Benchmark against frontier Claude models |
| Reviewing Results | [`6 Reviewing Results/`](./6%20Reviewing%20Results/) | Read the training curves and evaluation scores in MLflow |

Estimated end-to-end run time: **~2.5 hours**.

## Prerequisites

- **An AWS account.** For an AWS-run event, Workshop Studio provisions this for you. For a self-serve deployment (see below), you bring your own.
- **Region — `us-east-1` (N. Virginia).** This workshop was designed, tested, and validated in **US East (N. Virginia), `us-east-1`**, and that is the recommended region. Running it in any other region is **untested** — the SageMaker training/evaluation SDK, the Bedrock inference profiles, and the base model used for fine-tuning may not all be available everywhere. If you choose another region, it is up to you to first confirm that both the Amazon Bedrock models (below) and the Amazon SageMaker AI models and job types the labs use are available there; otherwise a lab can fail partway through. Whichever region you pick, everything must be created in that **one** region and you must not switch mid-workshop — later labs look for resources created by earlier ones.
- **Amazon Bedrock model access.** Lab 1 uses Bedrock to generate natural-language descriptions of extracted queries, and Lab 4 benchmarks against Anthropic Claude models on Bedrock. Both `us.anthropic.claude-haiku-4-5-20251001-v1:0` and `us.anthropic.claude-sonnet-4-6` need to be enabled in your region — verify their availability before deploying outside `us-east-1`.

## Getting Started

**If you have an event access code**, you are on the AWS Workshop Studio path — everything is already provisioned. Start at [`0 Getting Started/`](./0%20Getting%20Started/) and the rest of this README does not apply to you.

**If you are deploying into your own AWS account**, follow the next section first, then return to [`0 Getting Started/sm_studio/`](./0%20Getting%20Started/sm_studio/) to open Studio and start Lab 0.

---

## Deploying to your own account

The workshop's environment (VPC, Aurora Serverless v2 cluster, seeded `product_sales` table with query history, SageMaker Studio domain, JupyterLab space, IAM roles) is defined in a single CloudFormation template: [`0 Getting Started/aws_account/assets/workshop-stack.yaml`](./0%20Getting%20Started/aws_account/assets/workshop-stack.yaml).

The stack seeds Aurora at deploy time by reading two files from an S3 bucket **you provide**:

- `cosmetics_sales_synthetic_data.csv` — the synthetic sales dataset loaded into the `product_sales` table.
- `queries.txt` — the ~250 SQL statements replayed against the fresh cluster so `pg_stat_statements` has the query history Lab 1 extracts.

Both files are in this repo at [`0 Getting Started/aws_account/assets/`](./0%20Getting%20Started/aws_account/assets/) next to the template.

### Prerequisite: create a bucket and upload the two files

1. **Create an S3 bucket** in the region you plan to deploy into. Any name works; it just needs to be in the same region as the stack. The stack copies the two files out of this bucket into its own workshop bucket at deploy time — nothing writes back to it.

   The commands below use `us-east-1`, the tested region (see [Prerequisites](#prerequisites)). Deploying elsewhere is untested and requires you to confirm Bedrock and SageMaker AI model availability there first.

   ```bash
   export ASSETS_BUCKET=my-workshop-assets-$(date +%s)
   export AWS_REGION=us-east-1   # tested region — change at your own risk (see Prerequisites)
   aws s3 mb "s3://${ASSETS_BUCKET}" --region "${AWS_REGION}"
   ```

2. **Upload the two data files** from this repo's `0 Getting Started/aws_account/assets/` directory. You can place them at the bucket root or under any prefix (e.g. `workshop/`) — just remember what you chose; you pass it to the stack as `AssetsBucketPrefix`.

   ```bash
   # Option A — files at the bucket root (AssetsBucketPrefix = "")
   aws s3 cp "0 Getting Started/aws_account/assets/cosmetics_sales_synthetic_data.csv" "s3://${ASSETS_BUCKET}/"
   aws s3 cp "0 Getting Started/aws_account/assets/queries.txt"                        "s3://${ASSETS_BUCKET}/"

   # Option B — under a prefix (AssetsBucketPrefix = "workshop/")
   aws s3 cp "0 Getting Started/aws_account/assets/cosmetics_sales_synthetic_data.csv" "s3://${ASSETS_BUCKET}/workshop/"
   aws s3 cp "0 Getting Started/aws_account/assets/queries.txt"                        "s3://${ASSETS_BUCKET}/workshop/"
   ```

### Deploy the stack

Pass the bucket name and prefix as parameters. Every other parameter has a sensible default — see the `Parameters:` block at the top of the template for the full list (ACU sizing, retry tuning, JupyterLab instance type, etc.).

```bash
aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name workshop-sql-assistant \
  --template-file "0 Getting Started/aws_account/assets/workshop-stack.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AssetsBucketName="${ASSETS_BUCKET}" \
    AssetsBucketPrefix=""
```

Deploys take 15–25 minutes, most of it Aurora Serverless v2 provisioning. `CREATE_COMPLETE` on the stack means the cluster is up, `product_sales` is seeded, and `pg_stat_statements` holds the query history the labs need.

Once the stack is `CREATE_COMPLETE`, open SageMaker Studio and continue at [`0 Getting Started/sm_studio/`](./0%20Getting%20Started/sm_studio/).

### Cost

Unlike a Workshop Studio event account (which is reclaimed for free), a self-serve deployment is **billed to you**. The stack provisions:

- Aurora PostgreSQL Serverless v2 (scales 0.5–4 ACU by default)
- SageMaker Studio domain + `ml.t3.xlarge` JupyterLab space
- An MLflow tracking server (created by `00-setup.ipynb`, not the stack)
- GPU training jobs for SFT (Lab 2) and RLVR × 2 arms (Lab 3), plus evaluation jobs
- Bedrock inference for ~250 Claude calls

Estimate before you deploy: [SageMaker AI pricing](https://aws.amazon.com/sagemaker/ai/pricing/), [Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). End-to-end a single run typically fits comfortably inside a small experimental budget, dominated by the GPU training jobs.

### Cleanup

```bash
aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name workshop-sql-assistant
```

The stack's `CopyAssetsFunction` empties both workshop-owned S3 buckets on delete, so `DELETE_COMPLETE` fully tears the environment down. Two things are **not** touched by the stack and need manual cleanup if you want them gone:

- The **assets bucket you created above** (delete it yourself once the stack is fully deleted).
- The **MLflow tracking server** `workshop-mlflow`, created by Lab 0. Delete it from the SageMaker AI console under **MLflow**.

### Production considerations

The template is intentionally tuned for a **disposable, single-event workshop account** — it is not a production reference. A security scan of the stack flags several deliberate trade-offs that you should revisit before adapting it for a persistent or shared environment. Each is documented inline in the template; the important ones are collected here with the changes to make.

> These are hardening steps for production adopters. **None are required to run the workshop** — the defaults are appropriate for a throwaway event account that is reclaimed afterward.

**1. Encrypt with a customer-managed KMS key (CMK) instead of AWS-managed keys.** Aurora, both S3 buckets, and the Secrets Manager secret are all encrypted at rest, but with AWS-managed keys (`aws/rds`, SSE-S3 `AES256`, `aws/secretsmanager`). A CMK adds scheduled key rotation, CloudTrail decrypt auditing, and key-policy control over who can decrypt.

```yaml
# AuroraCluster.Properties
StorageEncrypted: true
KmsKeyId: !Ref YourCmkArn          # add this

# SlmWeightsBucket / SlmWeightsLoggingBucket — BucketEncryption
- ServerSideEncryptionByDefault:
    SSEAlgorithm: aws:kms          # was AES256
    KMSMasterKeyID: !Ref YourCmkArn

# RDSSecret.Properties
KmsKeyId: !Ref YourCmkArn          # add this
```

**2. Scope the two `Resource: '*'` IAM statements on `SageMakerExecutionRole`.** Two write-bearing statements are left account-wide for workshop pragmatism:

- `LineageTracking` (`CreateArtifact`/`CreateContext`/`CreateAction`/`AddAssociation`, …) — scope to the lineage resource types the workshop actually produces rather than `*`:

  ```yaml
  Resource:
    - !Sub 'arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:artifact/*'
    - !Sub 'arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:context/*'
    - !Sub 'arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:action/*'
    - !Sub 'arn:${AWS::Partition}:sagemaker:${AWS::Region}:${AWS::AccountId}:model-package/*'
    # ...plus the training-job/processing-job/model types the pipeline tracks
  ```
  Validate with a full Lab 2–4 run: lineage writes target the resource *being tracked*, so an over-tight list surfaces as `AccessDenied` mid-pipeline.

- `SageMakerReads` (`Describe*`/`List*`/`Search`) stays `*` because account-level `List*`/`Search` reject resource-level scoping — but it is **read-only**, so the residual exposure is visibility, not mutation. Leave it, and note the trade-off.

**3. Replace the broad `AmazonS3ReadOnlyAccess` managed policy** with a scoped read policy once you confirm the JumpStart / Deep Learning Container bucket names for your region. The template comment lists a concrete starting set (`SlmWeightsBucket`, the SageMaker default bucket, `jumpstart-cache-prod-<region>`, `sagemaker-sample-files`, and the regional DLC bucket). Scope too tightly and the base-model download fails at runtime, so validate with a full training run.

**4. `aws-marketplace:Subscribe` remains `Resource: '*'`** — the action supports neither resource-level permissions nor a `ProductId` condition key, so the `aws:CalledViaLast: bedrock.amazonaws.com` condition is the tightest available restriction (it limits the grant to calls Bedrock makes on the role's behalf). Recheck whether a `ProductId` condition key has since become available; if so, pin it to the Claude product IDs. Otherwise this is a documented, API-imposed over-grant.

**5. Durability defaults are minimized for a throwaway cluster.** `BackupRetentionPeriod` defaults to `1` day and `DeletionProtection` is `false` so the stack tears down cleanly. For anything you cannot recreate from the seed data, raise `BackupRetentionPeriod` (up to 35) for point-in-time recovery and set `DeletionProtection: true`.

**6. Your own permissions.** Deploying and running this yourself, you need an identity with permission to create the stack's resources (IAM roles, Aurora, S3, SageMaker domain/space, Lambda) via CloudFormation, and to open the deployed SageMaker Studio domain. Scope those to the workshop's resources rather than using account-wide admin.

For the full rationale behind every one of these choices, read the inline comments in [`workshop-stack.yaml`](./0%20Getting%20Started/aws_account/assets/workshop-stack.yaml) and the encryption / permissions notes in [`index.en.md`](./index.en.md).

---

## Repository layout

```
.
├── 0 Getting Started/         # Account access, Studio, JupyterLab
│   └── aws_account/assets/    # CloudFormation template + seed data
├── 1 Environment Setup/       # Lab 0
├── 2 Data Preparation/        # Lab 1
├── 3 Supervised Fine-Tuning/  # Lab 2
├── 4 RLVR Training/           # Lab 3
├── 5 Model Evaluation/        # Lab 4
├── 6 Reviewing Results/       # MLflow walk-through
├── images/                    # Screenshots and the architecture diagram
├── index.en.md                # Full workshop introduction
├── CONTRIBUTING.md
├── LICENSE
└── SECURITY.md
```

The `.en.md` filenames come from AWS Workshop Studio's localization convention and render as ordinary Markdown on GitHub.

## License, contributing, security

- License — see [`LICENSE`](./LICENSE).
- Contributing — see [`CONTRIBUTING.md`](./CONTRIBUTING.md).
- Security issue reporting — see [`SECURITY.md`](./SECURITY.md).
