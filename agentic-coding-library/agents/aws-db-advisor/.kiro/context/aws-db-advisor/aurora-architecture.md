# Aurora PostgreSQL Architecture, Scaling & Storage

Aurora internals (buffer caches, log applicator, CCM), mixed provisioned/Serverless v2 clusters, I/O-Optimised vs Standard, Serverless v2 scaling behaviour.

**Prerequisites:** This guide assumes familiarity with PostgreSQL concepts and AWS database services. For introductory content, see the [Aurora PostgreSQL documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraPostgreSQL.html).

**Glossary:** ACU = Aurora Capacity Unit (unit of compute for Serverless v2; 1 ACU ≈ 2 GiB RAM). CCM = Cluster Cache Management. FDW = Foreign Data Wrapper. HNSW = Hierarchical Navigable Small World (graph-based vector index algorithm). LSN = Log Sequence Number. MTR = Mini-Transaction (atomic unit of redo log application). VDL = Volume Durable LSN (highest LSN durably stored). WAL = Write-Ahead Log.


## 1. Aurora PostgreSQL architecture and scaling

### Mixed provisioned/Serverless v2 clusters

Aurora supports mixing provisioned and Serverless v2 instances in the same cluster. This hybrid approach optimises costs for workloads with predictable writes but variable reads.

**Configuration patterns:**

1. **Provisioned writer + Serverless v2 replicas** (most common):
   - Writer: Fixed capacity (e.g., db.r6g.large)
   - Replicas: Scale within cluster's min/max ACU range
   - Use case: Predictable write workload, variable read workload

2. **Serverless v2 writer + Provisioned replicas** (less common):
   - Writer: Scales for variable write workload
   - Replicas: Fixed read capacity

3. **Mixed replicas** (provisioned + Serverless v2):
   - Some replicas fixed for baseline capacity
   - Some replicas scale for burst traffic

**Cost optimisation:**

Example: Provisioned writer (db.r6g.large = $0.192/hour) + Serverless v2 replica (4 ACU average = $0.48/hour) = $490/month vs all-Serverless v2 (8 ACU average) = $701/month. Savings: 30%.

**When to use:**
- Write workload is predictable and steady
- Read workload is variable or spiky
- Want cost predictability for writes, elasticity for reads

**Switching between provisioned and Serverless v2:**

Individual instances can be modified between provisioned and Serverless v2 in place using `modify-db-instance` with `--db-instance-class db.serverless` (or back to a provisioned class like `db.r8g.2xlarge`). The cluster must have a `ServerlessV2ScalingConfiguration` set. The modification causes a brief restart of the affected instance but does not require deleting and recreating it.

**Constraints:**
- `ServerlessV2ScalingConfiguration` (min/max ACU) applies to all Serverless v2 instances in the cluster
- Cannot set different ACU ranges per Serverless v2 instance
- Provisioned instances unaffected by cluster's ACU configuration

**Decision criteria:**
- Monitor writer ACU usage for 30 days
- If writer consistently stays within narrow range (e.g., 4-6 ACU): Consider provisioned writer
- If writer varies significantly (e.g., 2-15 ACU): Stay with Serverless v2 writer

CCM is not supported for Serverless v2 instances — see CCM subsection below for implications on failover.

**Aurora provisioned features not supported in Serverless v2:**

1. **Database Activity Streams (DAS):** Cannot audit database activity at database level
2. **Cluster Cache Management (CCM):** No cache pre-warming for failover (Aurora PostgreSQL only)
3. **Aurora Auto Scaling:** Cannot automatically add/remove read replicas based on CPU usage (not needed - Serverless v2 scales capacity instead)

**Features that work but require sufficient capacity:**

Some Aurora features work with Serverless v2 but may cause performance issues or out-of-memory errors if the capacity range is too low:
- Memory-intensive workloads
- Large connection pools
- Complex queries with large result sets

Recommendation: Set minimum ACU high enough to accommodate feature memory requirements. Monitor for out-of-memory errors and increase capacity range if needed.

References:
- [Supported Regions and Aurora DB engines for Aurora Serverless v2](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.ServerlessV2.html)
- [Requirements and limitations for Aurora Serverless v2](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.requirements.html)

### Shared storage with independent compute

Aurora separates computation from storage. All instances connect to the same distributed storage layer, but each compute instance maintains its own independent buffer cache.

- Single shared database managed by distributed storage engine
- Storage redundantly stored on six storage nodes
- Each compute instance attaches to storage over the network
- Minimal time to spin up new reader nodes (attach to existing storage)

### Buffer caches and the log applicator

Each Aurora instance has its own PostgreSQL shared_buffers. Each replica can cache different data based on its workload, and adding read replicas increases total available cache memory. Aurora supports up to 15 read replicas per cluster.

Aurora keeps reader buffer caches current through the **log applicator**. The writer sends the same redo log stream to both the storage nodes and all reader instances. Each reader processes this stream as follows:

1. If the log record refers to a page already in the reader's buffer cache, the reader applies the redo operation to that page in place (modifies the cached page).
2. If the page is not in the reader's buffer cache, the reader discards the log record. The page can be read from shared storage later if needed.

Neither case generates I/O against the storage volume. The log applicator is how Aurora achieves sub-100ms replication lag — readers apply changes to cached pages as they arrive, rather than re-reading pages from storage.

The log applicator does real work on the reader: parsing log records, acquiring latches on buffer pages, applying redo operations, and advancing the Volume Durable LSN (VDL). Under heavy write load on the writer, this consumes CPU and memory on every reader, even readers with no client query traffic. An undersized reader (e.g. a Serverless v2 instance pinned at minimum ACU) may struggle to keep up with the log stream from a heavily loaded writer.

The 2018 Aurora SIGMOD paper specifies the ordering rules: log records are shipped from the writer in mini-transaction (MTR) chunks, applied in LSN order, and applied atomically per MTR to ensure readers see structurally consistent data.

References:
- [Aurora Replicas — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/aurora-replication-options/aurora-replicas.html)
- [Planning I/O in Amazon Aurora — AWS Database Blog](https://aws.amazon.com/blogs/database/planning-i-o-in-amazon-aurora/)
- Verbitski et al. (2018). *Amazon Aurora: On Avoiding Distributed Consensus for I/Os, Commits, and Membership Changes.* SIGMOD 2018. Section 3.2–3.3.

### Cluster Cache Management (CCM)

CCM is a separate, additional mechanism on top of the log applicator. Where the log applicator keeps existing cached pages current, CCM pre-populates the cache with pages the reader doesn't have yet — specifically for failover readiness.

| | Log applicator (all readers, automatic) | CCM (tier-0 only, opt-in) |
|---|---|---|
| Direction | Writer → readers (redo log records) | Reader → writer (bloom filter), then writer → reader (full page contents) |
| What it does | Applies redo operations to pages already in cache; discards records for uncached pages | Pre-populates cache with frequently-used pages the reader hasn't cached |
| Purpose | Cache coherency — keeps cached pages current | Cache warming — fills cache for fast failover |
| Work on reader | Parse log records, apply redo to cached pages | Receive and store full pages |

When CCM is enabled:

1. The tier-0 reader sends a bloom filter of cached buffer addresses to the writer
2. The writer compares blocks and sends frequently-used buffers (usage count > 3) to the reader
3. The reader loads these pages into its buffer cache

CCM affects only replicas with promotion tier priority = 0. Non-designated replicas (tier > 0) still receive the log applicator stream but do not receive CCM page transfers.

Configuration:
- Set `apg_ccm_enabled` cluster parameter to 1
- Set promotion tier priority to 0 for designated failover replica(s)
- Supported for Aurora PostgreSQL 9.6.11+, 10.5+, and later

Verify: `SELECT * FROM aurora_ccm_status();`

**Serverless v2 limitation:**

CCM is not available for Aurora Serverless v2 instances. In mixed clusters:

- Provisioned writer + Serverless v2 replicas: CCM cannot be used
- Serverless v2 writer + Provisioned replicas: CCM cannot be used
- All provisioned instances: CCM works normally

The log applicator still operates on Serverless v2 readers — they receive and process the redo log stream. Only the CCM page pre-population is unavailable.

After failover without CCM, the new writer starts with whatever pages the log applicator had kept current in its cache, but pages it never cached (because it discarded those log records) must be read from storage on demand. This causes performance degradation until the cache warms naturally (minutes to hours depending on working set size).

**Trade-off decision:**
- Fast failover required: Use all-provisioned with CCM
- Cost optimisation priority: Use mixed cluster, accept slower failover (log applicator still operates)
- Both important: Use all-Serverless v2 with promotion tier strategy

### pgvector scaling strategy

- Vector similarity search is read-only, ideal for read replica distribution
- Each replica maintains independent buffer cache for vector indexes
- HNSW indexes benefit from being memory-resident
- Use promotion tier > 0 for read replicas (independent caches)
- Designate 1-2 replicas with tier 0 for CCM/failover
- Do not use CCM replicas for read distribution

Scaling guidance:

Scoped queries (per-user, per-tenant, per-device partitioning):
- Billions of vectors: Aurora/RDS pgvector with table partitioning. Per-partition HNSW or brute-force scan. Scales to hundreds of billions (see Ring case study in vector-and-ai.md).

Global unscoped queries (monolithic HNSW index):
- Up to ~50M vectors: Aurora pgvector with 3-5 read replicas
- 50M-500M vectors: Aurora pgvector with aggressive replica scaling + halfvec
- Above 500M vectors: OpenSearch with sharding (10-30M vectors per shard)

### Cross-AZ latency

- Cross-AZ latency: ~1.6 milliseconds
- Same-AZ latency: ~600 microseconds
- For high-throughput applications (6,000+ queries/second), same-AZ deployment between application and database reduces latency significantly
- Trade-off: Reduced availability (single AZ) vs improved performance
- Cross-AZ data transfer charges apply for traffic between Availability Zones

References:
- [Aurora PostgreSQL cluster cache management](https://aws.amazon.com/blogs/database/introduction-to-aurora-postgresql-cluster-cache-management/)
- [Aurora PostgreSQL auto scaling with cache pre-warming](https://aws.amazon.com/blogs/database/optimize-amazon-aurora-postgresql-auto-scaling-performance-with-automated-cache-pre-warming/)
- [Long-running read queries on Aurora PostgreSQL](https://aws.amazon.com/blogs/database/manage-long-running-read-queries-on-amazon-aurora-postgresql-compatible-edition/)


## 2. Aurora storage configurations

### I/O-Optimised vs Standard

Aurora I/O-Optimised:
- Compute: +30% per instance-hour (provisioned), +33% per ACU-hour (Serverless v2: $0.16 vs $0.12)
- Storage: $0.225/GB-month
- Zero charges for read and write I/O operations
- Write latency improvements, especially noticeable on larger instances
- Best when I/O spending exceeds 25% of total Aurora database spending
- Can save up to 40% on costs for I/O-intensive workloads

Aurora Standard:
- Compute: base rate (e.g. db.r7g.12xlarge = $6.633/hr, Serverless v2 = $0.12/ACU-hr)
- Storage: $0.10/GB-month
- I/O charges: $0.20 per million requests

The 30% compute uplift is consistent across all provisioned instance sizes. The pricing page shows separate rate tables for each configuration (usage type codes: `InstanceUsage:` for Standard, `InstanceUsageIOOptimized:` for I/O-Optimised).

Decision: Total Aurora database spending = storage + I/O + compute (ACU-hours or instance-hours). Calculate hypothetical I/O costs under Standard pricing. If I/O exceeds 25% of the combined total (storage + I/O + compute), I/O-Optimised is the correct choice. The 25% threshold already accounts for the compute and storage premiums.

### Switching between configurations

- I/O-Optimised to Standard: Anytime, no restrictions
- Standard to I/O-Optimised: Once every 30 days
- Non-NVMe instances: No downtime when switching
- NVMe-based instances (r6gd, r6id, r8gd): Brief restart required

### Validating I/O-Optimised is correct

**Cost Explorer method (easiest):**

1. Open AWS Cost Explorer, filter by "Amazon Relational Database Service", group by "Usage Type"
2. Identify line items: `Aurora:StorageIOUsage` (I/O), `Aurora:StorageUsage` (storage), `Aurora:ServerlessV2Usage` or `Aurora:InstanceUsage` (compute)
3. Calculate: `I/O cost / (Storage cost + I/O cost + Compute cost)`
4. If >25%, stay with I/O-Optimised. If <25%, switch to Standard.

**CloudWatch method:**

Collect 30 days of `VolumeReadIOPs` + `VolumeWriteIOPs` (Sum) and `VolumeBytesUsed` (Average). Calculate hypothetical Standard I/O cost = `(Total I/O operations / 1,000,000) x $0.20`. Compare against total spend including compute.

References:
- [Aurora storage configurations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html#aurora-storage-type)
- [Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/)


## 3. Aurora Serverless v2

### Scaling behaviour

- Configurable minimum: 0 ACU (scale-to-zero, enables auto-pause — $0 compute when paused) or 0.5–128 ACU (always-on minimum)
- Configurable maximum: 1–256 ACU
- Increments: 0.5 ACU steps; 0.5 ACU is the minimum billable unit when actively running
- Scale-up: Single-digit seconds per increment. Higher current capacity = larger increments = faster scaling
- Scale-down: Minutes (conservative to prevent thrashing)
- Connections remain open during scaling (non-disruptive)
- Billing: Per-second ACU consumption
- Cheapest configuration: Set minimum to 0 ACU. Compute cost is $0 when paused; on resume scales to 0.5 ACU (~$0.06/hour Standard, ~$0.08/hour I/O-Optimised). Storage charges ($0.10–$0.225/GB-month) continue regardless.

### Buffer cache during scaling

- Scale-up: Buffer cache expands but starts cold. Frequently accessed data must reload from storage.
- Scale-down: Objects evicted from buffer cache as memory released.
- Set minimum ACU high enough to keep working dataset in buffer cache during idle periods.
- Monitor `BufferCacheHitRatio` (target >99%).

### Zero ACU (auto-pause)

- Requires minimum ACU set to 0
- Pause trigger: No user connections for configurable period (5 minutes to 24 hours)
- Resume time: ~15 seconds (up to 30 seconds if paused >24 hours)
- No compute charges whilst paused (storage charges continue)
- On resume, scales to at least 0.5 ACU (minimum billable unit)
- RDS Proxy prevents auto-pause (maintains persistent connections)
- Logical replication, binlog replication, and global database primary clusters also prevent auto-pause

### Reader scaling

- Readers in promotion tiers 0-1: Scale with the writer. Cannot scale independently.
- Readers in promotion tiers 2-15: Scale independently based on own workload.
- Keep at least one reader in tier 0 or 1 for fast failover.

### Maximum connections

Provisioned PostgreSQL:
```
max_connections = LEAST({DBInstanceClassMemory}/9531392, 5000)
```

Serverless v2 PostgreSQL:

| Min ACU | Max ACU | max_connections |
|---------|---------|-----------------|
| 0 or 0.5 | <=8 | Memory-based |
| 0 or 0.5 | >=16 | 2,000 (capped) |
| >=1 | 16 | 3,360 |
| >=1 | >=32 | 5,000 |

For high-connection workloads, set minimum ACU >= 1. Changing ACU maximum requires a reboot for `max_connections` to take effect.

### Migration assessment

Use the official AWS tool to evaluate migration candidates:
- [Aurora Serverless v2 Migration Assessment Tool](https://github.com/aws-samples/sample-aurora-serverless-migration-assessment-tool)

Serverless v2 is a good fit when:
- Variable workload with significant idle periods
- Spiky traffic patterns
- Weighted average utilisation below 25%
- Unpredictable scaling requirements

Not recommended when:
- Consistent, uniform workload distribution
- High baseline utilisation
- Cost predictability required

Serverless costs ~4x per vCPU vs provisioned instances. Economical only if weighted average < 25% utilisation.

References:
- [Aurora Serverless v2](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html)
- [Serverless v2 pricing](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/User_DBInstanceBilling.html)
- [How Serverless v2 works](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.how-it-works.html)
- [Auto-pause documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
- [Scaling documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.how-it-works.html#aurora-serverless-v2.how-it-works.scaling)
- [Evaluating provisioned vs Serverless v2](https://aws.amazon.com/blogs/database/evaluating-the-right-fit-for-your-amazon-aurora-workloads-provisioned-or-serverless-v2/)
- [Database parameters impact on scaling](https://aws.amazon.com/blogs/database/understanding-how-certain-database-parameters-impact-scaling-in-amazon-aurora-serverless-v2/)
- [Migration guide](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.upgrade.html)
- [Requirements and limitations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.requirements.html)
