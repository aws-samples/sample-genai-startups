# AWS Bill Shock Preventer — Guidelines

## Cost Reference

Use these approximate monthly costs when estimating waste:

| Resource | Approximate Monthly Cost |
|----------|------------------------|
| Unassociated Elastic IP | $3.65 |
| NAT Gateway (idle, no data) | $32.40 |
| ALB (idle, no traffic) | $16.20 |
| NLB (idle, no traffic) | $16.20 |
| EBS gp2 100GB | $10.00 |
| EBS gp3 100GB | $8.00 |
| t3.micro (running) | $7.59 |
| t3.small (running) | $15.18 |

These are us-east-1 prices. Adjust for other regions if needed.

## Priority Classification

- **High**: Resource costing >$30/month with zero utilization, or missing budget alerts.
- **Medium**: Right-sizing opportunities (gp2→gp3, old-gen instances), old snapshots.
- **Low**: Detached ENIs, untagged resources, minor cost items.

## Common Startup Patterns

- Dev/test resources left running over weekends and nights.
- NAT Gateways created for VPC setups but no longer needed after architecture changes.
- EBS volumes orphaned after EC2 termination (default `DeleteOnTermination=false`).
- Load balancers from old deployments with no registered targets.
- No budget alerts because "we'll check the console manually."
