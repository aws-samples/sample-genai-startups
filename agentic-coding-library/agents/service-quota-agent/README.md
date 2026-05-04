# Service Quota Agent

Proactively audits your AWS service quotas, flags limits you're about to hit, and submits increase requests for you — before they cause a production outage.

## Why

New AWS accounts start with low default quotas. Startups scale fast and hit these invisible walls in production: you can't launch instances during a traffic spike, your Lambda functions get throttled during a launch, or your IaC deploy fails at the CloudFormation stack limit. By then it's too late — quota increase requests take hours to days.

This agent turns a reactive scramble into a 5-minute proactive check. It finds the problems, shows you the fixes, and submits the requests — all in one conversation.

## What It Does

- Scans 10+ AWS services and compares current usage against quota limits
- Flags quotas at >70% (warning) and >90% (critical) utilization
- Detects "quota drift" — previously-increased quotas you're outgrowing
- Projects time-to-breach using 30-day growth trends
- **Submits quota increase requests** via Service Quotas API (with your confirmation)
- **Creates AWS Support cases** for quotas requiring manual review (with your confirmation)
- Produces a shareable `quota-report.md` with request IDs for tracking
- Creates scaling readiness reports for planned growth events

## Setup

### Prerequisites

- AWS credentials configured (via `aws configure`, environment variables, or IAM role)
- IAM permissions needed:
  ```
  servicequotas:List*
  servicequotas:Get*
  servicequotas:RequestServiceQuotaIncrease
  support:CreateCase
  support:DescribeCases
  ec2:Describe*
  lambda:ListFunctions
  lambda:GetAccountSettings
  elasticloadbalancing:Describe*
  rds:DescribeDBInstances
  ecs:List*
  ecs:Describe*
  cloudformation:ListStacks
  sqs:ListQueues
  sns:ListTopics
  cloudwatch:GetMetricStatistics
  sts:GetCallerIdentity
  iam:List*
  s3:ListAllMyBuckets
  ```
  Note: `support:*` requires a Business or Enterprise AWS Support plan. Without it, the agent will provide console URLs and pre-written text instead.
- [Kiro CLI](https://kiro.dev/docs/cli/) installed

### Run the agent

```bash
kiro-cli chat --agent service-quota-agent
```

That's it. No config files, no parameters. The agent auto-detects your region and starts scanning.

## Example Prompts

### Quick audit
```
Audit my account
```
Scans all priority services in your current region and produces a full report.

### Audit and fix
```
Audit my account and submit increase requests for anything critical
```
Scans, identifies critical quotas, shows you what it will request, and submits after your approval.

### Scaling readiness
```
We're expecting 5x traffic next month, what quotas do I need to increase?
```
Projects your current usage at 5x, identifies every quota that would break, and offers to submit all increases.

### Specific service check
```
Check my Lambda quotas, we keep getting throttled
```
Deep-dives into Lambda quotas including concurrent execution limits and code storage.

### Multi-region expansion
```
We're expanding to eu-west-1 and ap-southeast-1, what should we pre-request?
```
Identifies quotas to request in new regions before you deploy.

### Pending request status
```
Do I have any pending quota increase requests?
```
Shows in-flight requests and flags any that were denied or are stale.

## Output

The agent produces two things:

1. **Chat summary** — highlights, top risks, and immediate next steps
2. **quota-report.md** — a structured markdown report with:
   - Executive summary (critical/warning/healthy counts)
   - Critical findings with recommended increases
   - Warning findings to monitor
   - Quota drift (previously-increased quotas being outgrown)
   - Pending request status
   - Submitted requests with IDs and status (if you approved increases)
   - Recommended next steps

## Confirmation Flow

The agent never submits requests without your approval:

```
I found 3 quotas that need increases:

| # | Service | Quota                              | Current | Request | Reason               |
|---|---------|-------------------------------------|---------|---------|----------------------|
| 1 | EC2     | Running On-Demand Standard instances | 20      | 60      | At 85%, need headroom |
| 2 | VPC     | VPCs per region                     | 5       | 10      | At 80%, scaling 3x   |
| 3 | Lambda  | Concurrent executions               | 1000    | 3000    | At 72%, trending up  |

Would you like me to submit these? You can say:
- "Submit all" to request all increases
- "Submit 1 and 3" to pick specific ones
- "Skip" to just keep the report
```

## Demo Walkthrough

1. Configure AWS credentials for a test account
2. Run `kiro-cli chat --agent service-quota-agent`
3. Type: `Audit my account`
4. The agent will:
   - Auto-detect your region
   - Scan EC2, VPC, Lambda, ELB, RDS, ECS, IAM, CloudFormation, S3, SQS/SNS
   - Produce a summary in chat and a `quota-report.md` file
5. Review the findings — look for any critical or warning quotas
6. Type: `Submit all` to have the agent submit the increase requests
7. The agent confirms each submission with a request ID
8. Try: `We're planning to scale 3x next month` for a scaling readiness check

**Author: Derrick Selempo**
