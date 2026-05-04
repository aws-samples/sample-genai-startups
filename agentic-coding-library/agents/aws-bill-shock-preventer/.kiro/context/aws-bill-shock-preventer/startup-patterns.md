# Common Startup Cost Anti-Patterns

## Zombie Resources
- Dev/test resources left running 24/7 (nights, weekends, holidays)
- EBS volumes orphaned after EC2 termination (`DeleteOnTermination=false` is the default for non-root volumes)
- Load balancers from old deployments with no registered targets
- NAT Gateways created for VPC setups but no longer needed after architecture changes
- Elastic IPs allocated for testing and never released
- EBS snapshots from AMI creation that accumulate indefinitely

## Right-Sizing Mistakes
- Using m5/c5 instances when m7g/c7g Graviton equivalents are 20-40% cheaper
- Keeping gp2 EBS volumes when gp3 is 20% cheaper with better baseline performance
- Running t3.large for workloads that only need t3.small

## Governance Gaps
- No AWS Budget alerts — "we'll just check the console" (they never do)
- No Cost Anomaly Detection — a misconfigured Lambda or runaway process goes unnoticed for days
- No tagging strategy — impossible to attribute costs to teams or projects
- No monthly cleanup cadence — resources accumulate silently

## Priority Classification
- **High**: Resource costing >$30/month with zero utilization, or missing budget alerts
- **Medium**: Right-sizing opportunities (gp2→gp3, old-gen instances), old snapshots
- **Low**: Detached ENIs, untagged resources, minor cost items (<$5/month)
