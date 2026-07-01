# AWS Database Essentials for Startups

Simplified reference for the agent. Present infrastructure details (VPC, subnets, security groups) only when the user explicitly asks — otherwise explain concepts in accessible terms.

## Aurora PostgreSQL Serverless v2 — The Default Recommendation

Why it's the default:
- PostgreSQL compatibility means every framework, ORM, and tool works out of the box
- Scales from 0 ACU (auto-pause) to 256 ACU in 0.5 ACU increments (1 ACU ≈ 2 GB RAM)
- Auto-pause: scales to zero ACU when idle — pay only storage ($0.10-0.225/GB-month); resumes to 0.5 ACU minimum when active
- Resume from pause: ~15 seconds
- Per-second billing for compute
- Up to 15 read replicas for read-heavy workloads
- 6-way storage replication (durable by default)
- Supports pgvector for AI/vector search, JSONB for flexible schemas, full-text search

What to tell startups:
- "It's PostgreSQL that auto-scales and can pause when you're not using it"
- "You won't outgrow it until you're well past Series B"
- "Migration from any PostgreSQL host is straightforward — it's the same engine"

When NOT to recommend Aurora:
- Budget under $10/month and traffic is minimal → RDS PostgreSQL db.t4g.micro (~$13/month)
- Purely key-value access patterns with no JOINs → DynamoDB
- Need zero-ops with pay-per-request → DynamoDB

### Cost Optimisation Tips (share when relevant)
- I/O-Optimised storage: switch when I/O costs exceed 25% of total Aurora spend (saves up to 40%)
- Reserved capacity: Database Savings Plans give up to 35% discount (1-year, no upfront)
- Mixed clusters: provisioned writer + Serverless v2 readers saves ~30% when write load is steady
- Auto-pause: set minimum ACU to 0 for dev/staging environments

## DynamoDB — When You Want Zero Ops

Best for:
- Simple key-value or document access patterns
- Serverless architectures (Lambda + API Gateway + DynamoDB)
- Session stores, user profiles, game state, IoT device data
- Apps where you access data by a known key, not by complex queries

What to tell startups:
- "No servers, no scaling decisions, no maintenance windows"
- "You pay per read/write — pennies at startup scale"
- "If you need JOINs or complex queries across tables, PostgreSQL is better"

Pricing model:
- On-demand: $1.25 per million writes, $0.25 per million reads
- Free tier: 25 GB storage + 25 WCU/RCU (enough for small apps permanently)

When NOT to recommend:
- Complex queries, JOINs, aggregations → Aurora PostgreSQL
- Full-text search → Aurora PostgreSQL or OpenSearch
- Reporting/analytics on DynamoDB data → use DynamoDB zero-ETL integration with Redshift (don't move to Aurora just for analytics)

## ElastiCache Valkey — When You Need Speed

Best for:
- Session storage, shopping carts
- Real-time leaderboards, counters
- Caching database query results
- Pub/sub for real-time features (typing indicators, presence)
- Semantic caching for AI apps (cache similar LLM requests to cut cost and latency)

What to tell startups:
- "Use ElastiCache with Valkey — it's the recommended engine, open-source, and fully compatible with Redis commands"
- "Add this when your database queries get slow — cache the hot data"
- "Great for sessions and real-time features"
- "Not a primary database — always pair with Aurora or DynamoDB"

### Valkey Vector Search (Valkey 8.2+)
- Native vector search at microsecond latency — lowest latency vector search on AWS
- Supports up to 32,768 dimensions, HNSW and FLAT indexes
- Up to 99% recall, billions of vectors across a cluster
- Available on all instance types (except data tiering nodes), all regions, no additional cost
- Multi-threaded: more CPUs = linear throughput increase for both queries and ingestion
- Best for: semantic caching, real-time recommendation serving, low-latency similarity search where data doesn't need to be durable
- Not durable — if the node restarts, vector indexes rebuild from the latest snapshot but non-vector indexes (tags, numeric) require backfill
- For durable vector search with similar speed, use MemoryDB instead

Starting cost: ~$50/month (cache.t4g.micro)

Tip: Always create with cluster mode enabled even if starting with one shard — it's free and lets you scale horizontally later without migration.

## OpenSearch — When You Need Search

Best for:
- Full-text search with typo tolerance and relevance ranking
- Faceted search (filter by price range, category, brand simultaneously)
- Log analytics and observability
- Hybrid search (keyword + vector) at scale

What to tell startups:
- "You probably don't need this at first — PostgreSQL full-text search handles basic search"
- "Add OpenSearch when you have 100K+ searchable items and need facets, fuzzy matching, or relevance tuning"

Starting cost: ~$80/month (t3.small.search)

### Provisioned vs Serverless
- Provisioned: fixed instance types, you manage capacity. Better for steady workloads where you can right-size.
- Serverless: auto-scales compute and storage, pay per OCU (OpenSearch Compute Unit). Better for variable/unpredictable workloads or when you don't want to manage capacity. Minimum ~$700/month (2 OCUs for indexing + 2 for search).
- For most startups: start with provisioned (cheaper at small scale). Consider Serverless only at >1TB or when traffic is highly variable.

## Amazon Timestream — For Time-series Data

Best for:
- IoT sensor data, metrics, telemetry
- Application performance monitoring
- Financial tick data

What to tell startups:
- "Purpose-built for data with timestamps — automatic hot/cold storage tiers"
- "If your data is ONLY time-series, use Timestream. If it's mixed with relational data, use Aurora with table partitioning"

## DocumentDB — For MongoDB Workloads

Best for:
- Teams already using MongoDB who want a managed AWS service
- Document-heavy workloads (content management, catalogues)
- Native vector search for document-centric AI apps

What to tell startups:
- "If you're already on MongoDB, DocumentDB is the easiest AWS path"
- "If you're starting fresh, Aurora PostgreSQL with JSONB gives you document flexibility plus relational power"

## Neptune Analytics — For Graph + Vector

Best for:
- Knowledge graphs, social networks, fraud detection
- GraphRAG — traversing entity relationships to improve AI retrieval
- Any workload where relationships between entities matter

What to tell startups:
- "Use this when your AI needs to understand how things connect — not just what's similar"
- "Most startups don't need a graph database. If you're not sure, you don't need one."

## Aurora DSQL — For Multi-Region Distributed SQL

Best for:
- Globally distributed apps needing strong consistency across regions
- 99.999% multi-region availability requirements
- Active-active writes in multiple regions

Free tier (permanent): 100,000 DPUs + 1 GB storage per month (~700K transactions). Scales to zero when idle.

Major limitations (as of early 2026):
- No PostgreSQL extensions (no pgvector, PostGIS, pg_cron, etc.)
- No foreign keys, views, triggers, or sequences
- No stored procedures or functions
- No temporary tables
- 3,000-row transaction limit (applies to INSERT, UPDATE, DELETE)
- No JSON/JSONB data types
- Optimistic concurrency control — apps must handle retry logic for write conflicts
- No logical replication or WAL access — zero-ETL integrations and PostgreSQL-based CDC tools do not work with DSQL
- Native CDC is available (public preview): DSQL captures row-level changes and publishes them to Amazon Kinesis Data Streams. No logical replication slots needed — operates independently at the storage layer. Limitations: unordered delivery, no table-level filtering, INSERT/UPDATE indistinguishable (both `op: "c"`), Kinesis is the only supported target, at-least-once delivery (consumers must be idempotent)
- Single database per cluster (named `postgres`); use schemas or separate clusters for isolation
- Available in 8 regions (expanding)

What to tell startups:
- "DSQL has a generous free tier and scales to zero, but it's not a drop-in PostgreSQL replacement — many common features are missing"
- "Start with Aurora PostgreSQL Serverless v2 in a single region. Consider DSQL only when you specifically need multi-region active-active writes with strong consistency"
- "If your ORM uses foreign keys, views, or triggers, DSQL won't work without significant refactoring"

When NOT to recommend:
- Single-region apps → Aurora PostgreSQL Serverless v2 is simpler, cheaper, and fully featured
- Apps using pgvector, foreign keys, views, or triggers → not supported on DSQL
- Read-heavy global apps → Aurora Global Database with read replicas is sufficient
- Most startups → they won't need multi-region strong consistency for years

## MemoryDB — Fastest Vector Search on AWS

Best for:
- Sub-millisecond vector search with full durability (data survives restarts and failovers)
- Real-time AI features where microseconds matter and data must persist
- Primary database for workloads needing both in-memory speed and multi-AZ durability
- Session stores, user profiles, and caching where data loss is unacceptable

How it differs from ElastiCache Valkey:
- MemoryDB is durable by default — data is replicated across multiple AZs with a transaction log. ElastiCache is a cache (data can be lost on failure).
- Both support Valkey engine and vector search
- Use MemoryDB when you need the speed of in-memory with the durability of a database
- Use ElastiCache when you're caching data that can be re-fetched from a primary database

Vector search capabilities:
- Native vector search (same as ElastiCache Valkey 8.2+)
- HNSW and FLAT indexes, up to 32,768 dimensions
- Microsecond latency, 99%+ recall
- Durable — vector indexes persist through restarts and failovers

Pricing model:
- On-demand nodes: billed per instance-hour (e.g. db.r7g.xlarge ~$0.43/hour in us-east-1)
- Data written: $0.20/GB (first 10 TB/month free)
- No free tier for nodes (unlike DynamoDB or Aurora auto-pause)
- Reserved nodes: up to 55% discount (1-year or 3-year terms)
- Data tiering (r6gd nodes): stores less-accessed data on SSD, up to 60% storage cost savings

Starting cost: ~$315/month (db.r7g.large, single shard with 1 replica)

What to tell startups:
- "MemoryDB is for when you need in-memory speed AND your data must survive failures — it's a durable database, not just a cache"
- "Start with pgvector or ElastiCache Valkey unless you have a proven need for durable sub-millisecond vector search"
- "It's more expensive than ElastiCache because you're paying for durability — there's no auto-pause or free tier for compute"

## The "I'm Already On X" Migration Paths

| Currently on | Simplest AWS path |
|-------------|-------------------|
| RDS PostgreSQL | Aurora PostgreSQL (snapshot migration or read replica promotion) |
| MongoDB / MongoDB Atlas | DocumentDB (compatible API) or Aurora PostgreSQL (if willing to restructure) |
| Firebase / Firestore | DynamoDB (similar NoSQL model) |
| MySQL / MariaDB | Aurora MySQL Serverless v2 or Aurora PostgreSQL (if open to switching) |
| SQLite | Aurora PostgreSQL Serverless v2 or RDS PostgreSQL |

## Choose Graviton Instances Whenever Possible

When a user is ready to pick instance types or moves beyond Serverless v2, always recommend Graviton (Arm-based) instances:

- Up to 40% better price-performance than comparable x86 instances
- Up to 60% less energy for the same performance — the single biggest lever for reducing carbon footprint
- Supported across Aurora, RDS, ElastiCache, OpenSearch, DocumentDB, Neptune, and MemoryDB
- Instance families: db.r7g / db.r8g (Aurora/RDS), cache.r7g (ElastiCache), r7g.*.search (OpenSearch)
- No application changes needed — same PostgreSQL/Valkey/OpenSearch engine, just cheaper and greener

What to tell startups:
- "When choosing database instances, look for Graviton families like db.r7g or cache.r7g — the 'r7g' means it's Graviton-powered, cheaper, and uses less energy"
- "Aurora Serverless v2 already runs on Graviton, so you get this by default"
- "When you move to provisioned instances, choose db.r7g or db.r8g over db.r6i or db.r5"

## Amazon Cognito — Auth for Your Web App

Startups building web apps need authentication. Cognito is the AWS-native option and often comes up alongside database selection.

### Free Tier (permanent, does not expire after 12 months)
- Essentials tier: 10,000 MAUs free per month (password + social login + passwordless/passkeys)
- Lite tier: 10,000 MAUs free per month (password + social login only)
- Lite tier (pre-Nov 2024 accounts): 50,000 MAUs free per month
- SAML/OIDC federation: 50 MAUs free per month (all tiers)
- Identity pools (federated identities): always free

### Pricing above free tier
- Essentials: $0.015/MAU (flat rate, all tiers)
- Lite: $0.0055/MAU (first 100K), $0.0046/MAU (next 900K), lower at scale
- Plus (threat protection): $0.02/MAU (no free tier)

### What to tell startups
- "Cognito Essentials gives you 10K MAUs free with no expiry"
- "At 100K MAUs on Essentials, Cognito costs ~$1,350/month. Lite tier is ~$495/month for the same scale"
- "Lite tier trades passwordless/passkeys for lower cost — $495/month at 100K MAUs vs $1,350 on Essentials"
- For auth pricing comparisons with third-party providers, refer to the respective provider's documentation

## What NOT to Discuss (Unless Asked)

- VPC configuration, subnets, security groups, NAT gateways
- Instance families and sizes (just say "it auto-scales")
- Replication internals, WAL, buffer cache management
- ACU formulas, max_connections calculations
- Promotion tiers, CCM, I/O-Optimised vs Standard details

Keep it simple. The user wants to build their app, not become a DBA.
