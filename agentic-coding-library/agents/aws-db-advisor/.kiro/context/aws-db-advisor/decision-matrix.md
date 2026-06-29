# Web App → AWS Database Decision Matrix

When a user says "I'm building a web app, what database should I use?", walk through this matrix. Ask what they're building, not what database features they want.

## Aurora Serverless v2 scaling facts

- Minimum ACU is 0, not 0.5. Setting minimum to 0 enables auto-pause.
- When paused: compute cost is $0. Only storage charges apply ($0.10–$0.225/GB-month).
- When resuming: scales to 0.5 ACU (the minimum billable unit while actively running).
- 0.5 ACU is what you pay while the database is serving queries, not the floor configuration.
- If a user asks for "zero cost at idle" or "cost nothing when not in use," the answer is auto-pause with 0 ACU minimum — not 0.5 ACU.
- RDS Proxy prevents auto-pause. Do not recommend both together.

## Simplicity Rule

If one database handles all of the user's stated requirements, recommend that single database — do NOT add a second service. Only recommend a multi-service architecture when the primary database cannot handle a stated requirement. Two services means two sets of ops, two billing dimensions, and data synchronisation overhead. The simpler architecture wins unless there is a concrete, stated need that forces the split.

## Quick-Start Defaults

If the user can't describe their app yet or just wants to start coding: **Aurora PostgreSQL Serverless v2**. It's PostgreSQL (the most widely supported engine), scales to zero when idle, and handles everything from a side project to a Series B workload without re-architecting.

## By App Type

### SaaS / Multi-tenant App
Examples: project management tool, CRM, invoicing platform, HR system, analytics dashboard

**Start with:** Aurora PostgreSQL Serverless v2
- PostgreSQL is the standard for SaaS — every ORM, migration tool, and framework supports it
- Row-Level Security for tenant isolation without separate databases
- Scales to zero when idle (pay ~$0.10-0.225/GB-month storage only)
- Grows to 256 ACUs without re-architecting

**Growth path:** Add read replicas when read-heavy queries slow down. Switch writer to provisioned instance when utilisation is steady (saves ~30% vs Serverless). Add RDS Proxy if using Lambda or microservices (connection pooling). For HA: add a reader in another AZ for ~30-sec failover. For DR: enable cross-region backups. See `ha-and-dr.md`.

**Ballpark cost:**
- Pre-launch / dev: ~$5-15/month (auto-pause, minimal storage)
- 1K-10K users: ~$50-200/month
- 10K-100K users: ~$200-800/month

### E-commerce / Online Store
Examples: product catalogue, shopping cart, order management, inventory

**Start with:** Aurora PostgreSQL Serverless v2
- Products, orders, inventory, customers are relational data — PostgreSQL handles this naturally
- ACID transactions for order processing (no overselling)
- JSONB columns for flexible product attributes (size, colour, specs) without schema changes
- Full-text search with tsvector for basic product search

**Add when needed:**
- ElastiCache (Valkey) for session storage and cart caching when traffic grows
- OpenSearch only if you need faceted search, typo tolerance, or relevance ranking across 100K+ products

**Ballpark cost:**
- Small store (<1K orders/month): ~$15-50/month
- Growing store (1K-50K orders/month): ~$100-400/month
- Add ElastiCache: +$50-150/month

### Content Site / Blog / CMS
Examples: blog, documentation site, news site, portfolio

**Start with:** Aurora PostgreSQL Serverless v2 (or RDS PostgreSQL if you want even simpler)
- Content is structured (posts, authors, categories, tags) — relational fits perfectly
- Auto-pause means near-zero cost for low-traffic sites
- RDS PostgreSQL (single-AZ, db.t4g.micro) is even cheaper if you don't need auto-scaling

**Simpler alternative:** If content is static or near-static, consider S3 + CloudFront (no database at all). Use a static site generator.

**Ballpark cost:**
- Low traffic blog: ~$5-15/month (Aurora auto-pause) or ~$15/month (RDS t4g.micro)
- Medium traffic: ~$30-100/month

### Marketplace / Two-sided Platform
Examples: freelancer marketplace, rental platform, booking system, food delivery

**Start with:** Aurora PostgreSQL Serverless v2
- Complex relational data: users (buyers + sellers), listings, transactions, reviews, messages
- ACID transactions for payments and bookings
- PostgreSQL's JSONB for flexible listing attributes per category

**Add when needed:**
- ElastiCache (Valkey) for real-time availability/inventory caching
- OpenSearch for listing search with filters, geo-search, relevance ranking

**Ballpark cost:**
- Early stage: ~$15-50/month
- Growing (10K+ users): ~$200-600/month

### Real-time / Chat / Collaboration App
Examples: chat app, collaborative editor, live dashboard, notification system

**Start with:** Aurora PostgreSQL Serverless v2 for persistent data (users, channels, message history)

**Add immediately:** ElastiCache (Valkey) or DynamoDB for the real-time layer
- ElastiCache: Sub-millisecond pub/sub, presence tracking, typing indicators. Best if you need speed.
- DynamoDB: Millisecond reads/writes, auto-scales per-request. Best if you want zero ops and pay-per-message pricing.

**Ballpark cost:**
- Small app: ~$30-80/month (Aurora + ElastiCache smallest)
- Growing: ~$150-500/month

### Gaming / Social App
Examples: mobile game backend, social feed, leaderboards, matchmaking, follower graphs, notifications

**Start with:** DynamoDB — BUT only if access patterns are known and fixed (get profile by ID, get leaderboard by score, get feed by user+time). DynamoDB requires you to design your keys and indexes upfront.

**Do NOT pick DynamoDB when:** the user says they need novel queries, evolving queries, ad-hoc queries, flexible queries, geospatial/proximity queries, or "I don't know what queries I'll need yet." These signal that access patterns will change — use Aurora PostgreSQL Serverless v2 instead (SQL handles any query shape without redesigning your data model, and PostGIS handles geospatial).

- Player profiles, game state, social graphs, and feeds are key-value access patterns — DynamoDB handles these natively
- Single-digit millisecond reads/writes at any scale
- On-demand pricing means zero cost when nobody's playing
- No servers to manage — ideal for small game studios and solo devs

**Add when needed:**
- ElastiCache (Valkey) for real-time leaderboards, matchmaking queues, and session state
- Aurora PostgreSQL if you need complex queries (inventory systems with JOINs, transactional data)
- DynamoDB zero-ETL integration with Redshift for analytics and reporting

**Ballpark cost:**
- Small (< 10K DAU): ~$5-25/month (DynamoDB on-demand, mostly free tier)
- Growing (10K-100K DAU): ~$50-300/month
- Add ElastiCache for leaderboards: +$50-150/month

### IoT Dashboard / Time-series App
Examples: sensor monitoring, fleet tracking, metrics dashboard, log analytics

**Start with:** Amazon Timestream (if data is purely time-series) or Aurora PostgreSQL with partitioning (if you also have relational data)
- Timestream: Purpose-built for time-series, automatic data lifecycle (hot → cold storage), SQL-compatible
- Aurora + pg_partman: Partition by time range, drop old partitions cheaply. Good when IoT data lives alongside user/device relational data.

**Ballpark cost:**
- Small (millions of data points/month): ~$20-60/month
- Medium (billions): ~$200-800/month

### AI / ML App (RAG, semantic search, recommendations)
Examples: AI chatbot with knowledge base, semantic search, recommendation engine, image similarity

**Start with:** Aurora PostgreSQL Serverless v2 with pgvector
- pgvector extension stores and searches vector embeddings alongside your relational data
- No separate vector database needed for vector indexes under ~50GB
- Same database for users, content, AND embeddings — simpler architecture

**Growth path:** If vector index exceeds ~100GB or you need advanced hybrid search (keyword + semantic), add OpenSearch. See `vector-and-ai.md` for detailed vector database selection by data type, scale, and AI pattern.

**Ballpark cost:**
- Small (index < 5 GB): ~$30-100/month
- Medium (index 5-50 GB): ~$200-600/month

## Decision Shortcuts

| Signal in conversation | Recommendation |
|----------------------|----------------|
| "I don't know my future queries" / "novel queries" / "queries will evolve" / "flexible queries" | Aurora PostgreSQL Serverless v2 — SQL handles any query shape without redesigning your data model. Do NOT recommend DynamoDB. |
| "I just want to start building" | Aurora PostgreSQL Serverless v2 |
| "I need it to be as cheap as possible" | DynamoDB (permanent free tier: 25GB + 25 WCU/RCU), RDS PostgreSQL db.t4g.micro ($13/month), or Aurora with auto-pause |
| "I'm using DynamoDB already" | Stay on DynamoDB unless you need JOINs or transactions across tables |
| "I need real-time updates" | Aurora for persistence + ElastiCache Valkey for real-time |
| "I have time-series data" | Timestream (pure time-series) or Aurora + partitioning (mixed) |
| "I need vector/AI search" | Aurora PostgreSQL + pgvector |
| "I'm already on PostgreSQL somewhere" | Aurora PostgreSQL Serverless v2 (easiest migration) |
| "I don't want to manage anything" | DynamoDB (truly zero-ops) or Aurora Serverless v2 (near-zero-ops) |
| "I need MongoDB-like flexibility" | DocumentDB (MongoDB-compatible) or Aurora PostgreSQL with JSONB |
| "I'm a MySQL shop" | Aurora MySQL Serverless v2 (same engine, same auto-scaling as Aurora PostgreSQL) |
| "I need multi-region writes" | Aurora DSQL (PostgreSQL-compatible, serverless, 99.999% multi-region availability) |
| "What about high availability?" | See `ha-and-dr.md`. Short answer: storage is always replicated across 3 AZs. Add a replica in another AZ for compute failover. Multi-region only if your business requires it. |
| "What if a region goes down?" | See `ha-and-dr.md`. Level 2 (cross-region backups) costs pennies. Level 3 (multi-region active) costs ~2x. DynamoDB Global Tables is the cheapest multi-region option. |
