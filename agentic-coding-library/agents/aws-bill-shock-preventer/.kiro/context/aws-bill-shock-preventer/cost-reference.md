# AWS Cost Estimation Reference

## Per-Resource Monthly Costs (us-east-1)

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| Unassociated Elastic IP | $3.65 | Charged per hour when not attached |
| NAT Gateway (idle) | $32.40 | $0.045/hr + $0.045/GB processed |
| ALB (idle) | $16.20 | $0.0225/hr minimum |
| NLB (idle) | $16.20 | $0.0225/hr minimum |
| EBS gp2 per GB | $0.10 | Per GB-month |
| EBS gp3 per GB | $0.08 | Per GB-month, 20% cheaper than gp2 |
| EBS snapshot per GB | $0.05 | Per GB-month |
| t3.micro | $7.59 | On-demand |
| t3.small | $15.18 | On-demand |
| t3.medium | $30.37 | On-demand |
| m5.large | $69.12 | On-demand |
| m7g.large | $58.77 | Graviton, ~15% cheaper than m5 |

## Savings Estimates by Action

| Action | Typical Savings |
|--------|----------------|
| gp2 → gp3 migration | 20% on EBS costs |
| Old-gen → Graviton | 20-40% on compute |
| Delete unattached EBS | 100% of volume cost |
| Release unused EIPs | $3.65/month each |
| Remove idle NAT GW | $32+/month each |
| Remove idle ALB/NLB | $16+/month each |

Prices are approximate us-east-1 on-demand rates. Adjust for other regions.
