# Capacity Finder Agent

Finds available EC2 Capacity Blocks and SageMaker Training Plan offerings across AWS regions — so you can reserve GPU/accelerator compute before it's gone.

## Why

GPU and accelerator capacity (P5, P6, Trn2, etc.) is scarce on AWS. EC2 Capacity Blocks and SageMaker Training Plans let you reserve dedicated instances, but availability varies by region, instance type, and timing. Checking manually through the console across 13+ regions is slow and you'll miss windows.

This agent scans all supported regions in one conversation, shows you what's available, and produces a shareable report.

## What It Does

* Searches EC2 Capacity Block offerings across all supported regions
* Searches SageMaker Training Plan offerings (training-job, hyperpod-cluster, endpoint)
* Supports all GPU/accelerator instance types: p4d, p4de, p5, p5e, p5en, p6-b200, p6-b300, trn1, trn2
* Presents results sorted by price, availability, and region
* Handles errors gracefully (unsupported regions, account restrictions)
* Produces a shareable `capacity-report.md`

## Setup

### Prerequisites

* AWS credentials configured (via `aws configure`, environment variables, or IAM role)
* IAM permissions needed:

  ```
  ec2:DescribeCapacityBlockOfferings
  sagemaker:SearchTrainingPlanOfferings
  sts:GetCallerIdentity
  ```

  Note: SageMaker Training Plans require your account to be allowlisted. If you see "account is not allowed" errors, open an AWS Support case requesting access.

* [Kiro CLI](https://kiro.dev/docs/cli/) installed

### Run the agent

```
kiro-cli chat --agent capacity-finder-agent
```

No config files or parameters needed. Describe what capacity you need and the agent searches for it.

## Example Prompts

### Find specific capacity

```
Find p5.48xlarge capacity for 8 instances in us-east-2 for 14 days
```

### Search all regions

```
Search for trn2.48xlarge in all regions for 182 days starting next week
```

### SageMaker Training Plans

```
Find SageMaker training plan offerings for p5.48xlarge, 4 instances, 30 days
```

### Compare options

```
What p5 or trn2 capacity is available anywhere for at least 7 days?
```

### Broad search

```
Show me all available GPU capacity blocks in us-east-1 and us-west-2
```

## Output

The agent produces two things:

1. **Chat summary** — best options, pricing highlights, and recommendations
2. **capacity-report.md** — a structured markdown report with:
   * Search parameters used
   * All offerings found (EC2 and SageMaker)
   * Errors by region
   * Recommendations (best value, earliest available, longest duration)

## Supported Instance Types

| Family | Types |
|--------|-------|
| P6 | p6-b200.48xlarge, p6-b300.48xlarge |
| P5 | p5.4xlarge, p5.48xlarge, p5e.48xlarge, p5en.48xlarge |
| P4 | p4d.24xlarge, p4de.24xlarge |
| Trainium | trn1.32xlarge, trn2.48xlarge, trn2.3xlarge |

## Supported Regions

us-east-1, us-east-2, us-west-1, us-west-2, eu-north-1, eu-west-2, ap-northeast-1, ap-northeast-2, ap-south-1, ap-southeast-2, ap-southeast-3, ap-southeast-4, sa-east-1

## Demo Walkthrough

1. Configure AWS credentials for your account
2. Run `kiro-cli chat --agent capacity-finder-agent`
3. Type: `Find p5.48xlarge capacity in all regions for 14 days`
4. The agent will:
   * Scan all 13 supported regions
   * Report which regions have availability
   * Show pricing and date details
   * Produce a `capacity-report.md` file
5. Try: `Now search for SageMaker training plans for the same instance type`
6. Try: `What's the cheapest option for trn2.48xlarge for a week?`
