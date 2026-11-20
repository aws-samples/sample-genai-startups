# Production Readiness Checklist: 5 Pillars

30 items across 5 pillars: security, cost, resilience, observability, and governance. Each item has a severity (CRITICAL or IMPORTANT) and the check mode (IaC = code analysis, Live = AWS API). CRITICAL means fix before launch: never recommend shipping to production while a CRITICAL item is open. Hardcoded credentials (S6, P5) and security groups open to the internet beyond 80/443 on a load balancer (P3) are always CRITICAL.

## 🔒 Security (SSB-aligned)

| # | Check | Severity | Mode | What to look for |
|---|-------|----------|------|------------------|
| S1 | Root account MFA | CRITICAL | Live | IAM GetAccountSummary: AccountMFAEnabled = 1 |
| S2 | No IAM access keys for root | CRITICAL | Live | Root account has no access keys |
| S3 | Encryption at rest | CRITICAL | IaC+Live | KMS/SSE on S3, RDS, DynamoDB, EBS |
| S4 | No public S3 buckets | CRITICAL | IaC+Live | PublicAccessBlockConfiguration on all buckets |
| S5 | HTTPS enforced | IMPORTANT | IaC | ALB/CloudFront listeners use HTTPS, redirect HTTP |
| S6 | IAM roles over access keys | CRITICAL | IaC | ECS/Lambda/EC2 use IAM roles; no access keys or other credentials hardcoded in code or config |

## 💰 Cost

| # | Check | Severity | Mode | What to look for |
|---|-------|----------|------|------------------|
| C1 | No oversized instances | IMPORTANT | IaC+Live | Dev environments on t3.micro/small, not m5.xlarge |
| C2 | NAT Gateway optimization | IMPORTANT | IaC | Single NAT GW for dev, multi-AZ for prod only |
| C3 | Unused resources | IMPORTANT | Live | Unattached EBS volumes, idle load balancers |
| C4 | Tagging strategy | IMPORTANT | IaC+Live | Resources tagged with Environment, Project, Owner |
| C5 | Auto-scaling configured | IMPORTANT | IaC | ASG or ECS service auto-scaling for variable workloads |
| C6 | Right storage tier | IMPORTANT | IaC | S3 lifecycle policies, GP3 over GP2 for EBS |

## 🔄 Resilience (SRB-aligned)

| # | Check | Severity | Mode | What to look for |
|---|-------|----------|------|------------------|
| R1 | Database backups enabled | CRITICAL | IaC+Live | RDS automated backups, DynamoDB PITR |
| R2 | Multi-AZ for production DB | CRITICAL | IaC+Live | RDS MultiAZ=true for production |
| R3 | Health checks configured | IMPORTANT | IaC | ECS/ELB health checks with appropriate thresholds |
| R4 | Auto-recovery for compute | IMPORTANT | IaC | ASG min=1 or ECS desired>0 for self-healing |
| R5 | Error handling in code | IMPORTANT | IaC | Try/catch, retry logic, circuit breakers in app code |
| R6 | Deployment strategy | IMPORTANT | IaC | Rolling updates or blue/green, not all-at-once |

## 📊 Observability

| # | Check | Severity | Mode | What to look for |
|---|-------|----------|------|------------------|
| O1 | CloudWatch alarms exist | CRITICAL | IaC+Live | Alarms for CPU, memory, 5xx errors, latency |
| O2 | Centralized logging | IMPORTANT | IaC+Live | CloudWatch Log Groups for all services |
| O3 | Structured logging | IMPORTANT | IaC | JSON logging format, correlation IDs |
| O4 | Dashboard configured | IMPORTANT | Live | CloudWatch dashboard with key metrics |
| O5 | Alerting configured | IMPORTANT | IaC+Live | SNS topics connected to alarms |
| O6 | Tracing enabled | IMPORTANT | IaC | X-Ray or OTEL tracing for distributed services |

## ✅ Governance (technical controls observed)

This pillar records technical controls you can observe in the code or the account. Report each item as observed, missing, or not assessed, with its evidence (file and line, or the API result). These controls are often useful when a team later prepares for an audit, but this pillar does not measure readiness for, or conformance with, SOC 2, GDPR, HIPAA, ISO 27001 or any other framework. Never give a framework readiness score, percentage, pass/fail verdict, or a "compliant" or "non-compliant" statement.

| # | Check | Severity | Mode | What to look for |
|---|-------|----------|------|------------------|
| P1 | CloudTrail enabled | CRITICAL | Live | Trail active in at least one region |
| P2 | VPC with private subnets | IMPORTANT | IaC | Databases and app servers in private subnets |
| P3 | Security groups least privilege | CRITICAL | IaC | No 0.0.0.0/0 ingress except port 80/443 on ALB |
| P4 | Data residency awareness | IMPORTANT | IaC | Resources deployed in expected region(s) |
| P5 | Secrets management | CRITICAL | IaC | Secrets in SSM/Secrets Manager, not env vars or code |
| P6 | Dependency scanning | IMPORTANT | IaC | Dependabot, Snyk, or similar configured |
