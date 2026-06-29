# Cost Optimisation for AWS Databases

Database Savings Plans, Reserved Instances, ElastiCache pricing, S3 PUT cost trap, CloudFront origins.

**Note:** Pricing examples are shown in USD for the us-east-1 region. Costs vary by region and currency. Use the [AWS Pricing Calculator](https://calculator.aws) for region-specific estimates.


## 6. Database Savings Plans

- Discount: Up to 35% vs On-Demand
- Term: 1 year
- Payment: No Upfront only (monthly billing)
- Commitment: $/hour usage commitment

Coverage: Aurora (provisioned and Serverless v2), RDS (all engines), DynamoDB, ElastiCache (Valkey only — Redis OSS excluded), DocumentDB, Neptune, Keyspaces, Timestream, DMS, OpenSearch.

### Instance generation restriction

Database Savings Plans cover Generation 7 and newer provisioned instances only (e.g. db.r7g, db.r8g, cache.r7g). Older generations (db.r5, db.r6g, db.r6i, cache.r6g, cache.r6gd, etc.) are not eligible.

Serverless usage is covered regardless of generation: Aurora Serverless v2, ElastiCache Serverless for Valkey, DocumentDB Serverless, Neptune Serverless, OpenSearch Serverless.

DynamoDB and Keyspaces: on-demand and provisioned throughput covered (no instance generation concept).

ElastiCache: Valkey instances only. Redis OSS instances are excluded even on gen 7+ hardware.

Timestream: InfluxDB instances only.

### Flexibility

Change instance families/sizes within gen 7+, move between regions, switch between provisioned and serverless, migrate between database engines — all while retaining the discount.

### Interaction with Reserved Instances

Cannot combine with Reserved Instances on the same workload. Can use RIs for one workload and Savings Plans for another. RIs still cover older generations (r5, r6g, etc.) that Savings Plans do not. As RIs expire, migrate to gen 7+ and switch to Savings Plans.

References:
- [Database Savings Plans pricing](https://aws.amazon.com/savingsplans/database-pricing/)
- [Savings Plans FAQs](https://aws.amazon.com/savingsplans/faqs/)
- [Savings Plans types](https://docs.aws.amazon.com/savingsplans/latest/userguide/plan-types.html)


## 21. Cheapest Aurora configuration (scale-to-zero)

Aurora Serverless v2 supports a minimum ACU of 0, which enables auto-pause. When paused:

- Compute cost: $0 (no ACU charges)
- Storage cost: continues at $0.10/GB-month (Standard) or $0.225/GB-month (I/O-Optimised)
- Resume time: ~15 seconds (up to 30 seconds if paused >24 hours)
- On resume: scales to 0.5 ACU minimum (~$0.06/hour Standard, ~$0.08/hour I/O-Optimised)

This is the cheapest possible Aurora deployment for intermittent workloads. Total cost for a 10 GB database used 2 hours/day: ~$1/month storage + ~$3.60/month compute = ~$4.60/month.

Constraints that prevent auto-pause: RDS Proxy connections, logical replication, binlog replication, global database primary clusters. If any of these are active, the instance remains at minimum 0.5 ACU.

For the absolute cheapest relational database on AWS regardless of engine, compare: Aurora Serverless v2 (0 ACU) vs RDS db.t4g.micro ($0.016/hour = ~$11.52/month always-on, no scale-to-zero). Aurora wins for workloads active <6 hours/day; RDS db.t4g.micro wins for always-on light workloads.


## 22. S3 PUT cost trap for high-write workloads

S3 + CloudFront is a common pattern for serving static content at scale. It does not work for workloads that rewrite millions of objects frequently.

S3 PUT pricing is $5 per million requests. For a workload that rewrites 10M objects hourly:

- 10M PUTs/hour × 24 × 30 = 7,200M PUTs/month × $0.005 per 1,000 = $36,000/month in PUTs alone

This makes S3 uneconomical compared to DynamoDB or Valkey for profile stores, session stores, or any pattern where objects are rewritten on a schedule across millions of keys.

S3 + CloudFront works well when:

- Write volume is low (content published once, read many times)
- Objects are large (amortises the per-request cost)
- TTL-based freshness is acceptable

It does not work when:

- Millions of objects are rewritten hourly or more frequently
- The workload is write-heavy relative to reads


## 23. CloudFront origins for database-backed content

CloudFront cannot query DynamoDB, ElastiCache, or any database directly. Serving database-backed content through CloudFront requires a compute origin:

- Lambda function URLs
- Lambda@Edge
- EKS/ECS service behind an ALB
- API Gateway

This compute layer adds cost and latency to the serving path.

S3 is the only AWS storage service that CloudFront can use as a native origin without a compute layer. For S3 origins, data transfer from S3 to CloudFront is free.

When comparing profile store options behind CloudFront, the compute origin cost applies equally to all database-backed options (DynamoDB, Valkey, Aurora, etc.) and is not a differentiator between them.


## 24. Database Savings Plans vs Reserved Instances for ElastiCache

### Pricing API limitation

The AWS Price List API (and pricing MCP tools) returns on-demand and Reserved Instance pricing only. Database Savings Plan rates are published on a separate index and are not available through the Price List API. Use calculator.aws or the Savings Plans pricing page for Savings Plan rates.

### Discount comparison for ElastiCache Valkey r7g

Database Savings Plans advertise "up to 35%" discount, but the actual discount varies by service and instance family.

For ElastiCache Valkey r7g instances:

- Database Savings Plan (1-year, no upfront): ~20% discount off on-demand
- Reserved Instance (1-year, no upfront): ~32% discount off on-demand
- Reserved Instance (1-year, all upfront): ~36% discount off on-demand

Database Savings Plans offer less discount but more flexibility — they apply across instance families, sizes, regions, and even across different database services (Aurora, RDS, DynamoDB, ElastiCache, DocumentDB, Neptune, etc.).

Reserved Instances offer deeper discounts but lock you to a specific instance type and region.

Do not use the "up to 35%" headline figure in customer-facing cost estimates. Use the actual rate from calculator.aws for the specific instance type.
