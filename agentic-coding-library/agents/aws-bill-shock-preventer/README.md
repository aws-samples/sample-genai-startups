# aws-bill-shock-preventer

A Kiro agent that scans your AWS account for cost waste, idle resources, right-sizing opportunities, and missing governance controls — then delivers a prioritized savings report with remediation commands.

## Capabilities

The agent runs 4 analysis phases across 14 checks:

**Phase 1 — Cost Overview**
- Daily spend trend (last 7 days)
- Top 5 services by cost (current month)

**Phase 2 — Zombie Resources**
- Unattached EBS volumes
- Unassociated Elastic IPs (~$3.65/month each)
- Old EBS snapshots (>90 days)
- Idle Load Balancers (no healthy targets, ~$16/month each)
- Stopped EC2 instances (EBS still billed)
- Detached network interfaces
- Idle NAT Gateways (~$32/month each)

**Phase 3 — Right-Sizing**
- Old-generation EC2 instance types (not Graviton/current-gen)
- gp2 EBS volumes (gp3 is ~20% cheaper)

**Phase 4 — Governance Gaps**
- Missing AWS Budget alerts
- Missing Cost Anomaly Detection monitors
- Untagged resources (no Environment/Owner tags)

## Prerequisites

- [Kiro CLI](https://kiro.dev) installed
- AWS credentials configured with read access to: EC2, EBS, ELB, Cost Explorer, Budgets, Resource Groups Tagging API
- `jq` installed (for test validation)

## Installation

Copy the `aws-bill-shock-preventer` directory into your workspace's `agents/` folder, then launch:

```bash
kiro-cli agent chat --path agents/aws-bill-shock-preventer/.kiro/agents/aws-bill-shock-preventer.json
```

## Example Prompts

**Full scan:**
> "Scan us-east-1 for all cost waste and bill shock risks."

Expected output:
```
Executive Summary (us-east-1)
- Total estimated monthly waste: ~$51/month ($612/year)
- Findings: 3 zombie resources, 0 right-sizing, 3 governance gaps
- Top action: Release 1 unassociated Elastic IP → save $3.65/month

Findings:
| # | Resource | Region | Issue | Est. Savings | Priority |
|---|----------|--------|-------|-------------|----------|
| 1 | eipalloc-0abc123 | us-east-1 | Unassociated EIP | $3.65/mo | Medium |
| 2 | nat-0def456 | us-east-1 | Idle NAT Gateway | $32/mo | High |
| 3 | — | us-east-1 | No AWS Budget configured | — | High |
```

**Zombie resources only:**
> "Find all idle and unused resources in us-east-1 that are costing me money."

Expected output: A list of unattached EBS volumes, unassociated EIPs, old snapshots, idle load balancers, stopped instances, detached ENIs, and idle NAT gateways with estimated monthly waste per resource.

**Governance check:**
> "Do I have budget alerts and cost anomaly detection set up?"

Expected output: Whether AWS Budgets and Cost Anomaly Detection monitors are configured, plus a sample of untagged resources with remediation commands.

## Running Tests

Ensure AWS credentials are exported, then from the repo root:

```bash
# Run all tests (3 runs each, 90% success rate)
python3 ./agentest.py aws-bill-shock-preventer

# Run a specific test
python3 ./agentest.py aws-bill-shock-preventer 1-cost-overview -n 1

# Available tests:
# 1-cost-overview          — Validates Phase 1 (daily spend + top services)
# 2-zombie-resources       — Validates Phase 2 (idle/unused resources)
# 3-rightsizing-opportunities — Validates Phase 3 (old-gen instances, gp2 volumes)
# 4-governance-gaps        — Validates Phase 4 (budgets, anomaly detection, tagging)
```

## How It Works

The agent uses the built-in `aws` tool (AWS CLI) to make read-only API calls. No MCP servers are required. It follows a structured prompt that defines exactly which checks to run and how to interpret results, ensuring consistent and reliable output across runs.

## Limitations

- Analyzes one region at a time (ask the agent to scan additional regions)
- Read-only — never modifies resources (remediation commands are provided for the user to review and execute)
- Cost estimates use approximate us-east-1 public pricing
- Requires appropriate IAM permissions for all API calls

**Author: Katia Kissin**
