# ElastiCache Valkey & Data Tiering

Valkey as profile/session store, data tiering 5% threshold, MariaDB/MySQL query cache.


## 20. MariaDB vs MySQL query cache

### Key findings

- MySQL removed query cache entirely in version 8.0 due to scalability issues
- MariaDB retained query cache for backwards compatibility but disabled by default
- Both implementations suffer from mutex contention on multi-core systems
- Query cache doesn't scale well with high-throughput workloads

### Main issues

- Global mutex bottleneck
- Aggressive invalidation on any table modification
- Lock blocking causing query backlogs
- Poor performance on multi-core systems

Modern alternatives: application-level caching (Redis, Memcached) or ProxySQL.


## 21. ElastiCache Valkey as a profile/session store

### When Valkey beats DynamoDB for profile stores

If the data is regenerable (e.g. recomputed hourly from a pipeline) and durability is not required (the application falls back gracefully), Valkey on a flat node cost beats DynamoDB's per-request pricing at high throughput.

DynamoDB costs scale linearly with request volume (per-RRU/WRU). Valkey costs are fixed per node regardless of throughput. At high read/write volumes (thousands of requests per second), the flat cost wins.

Example: 30M profiles at 3 KB, 10M DAU, hourly reads and writes.

- DynamoDB provisioned (2× average, auto-scaling): ~$8,199/month. Writes dominate (3 WRU per 3 KB write).
- ElastiCache Valkey r7g.4xlarge (2 nodes, Multi-AZ): ~$2,038/month on-demand.

Valkey is 75% cheaper in this scenario. The trade-off is no durability — if both nodes fail, data must be rehydrated from the source pipeline.

### Cluster mode: enable at creation

Valkey supports cluster mode (data sharding across multiple nodes). Cluster mode must be enabled at cluster creation — it cannot be added later without creating a new cluster and migrating data.

Recommendation: always create the cluster with cluster mode enabled, even with a single shard. No cost difference, and the horizontal scaling path is available without migration if the dataset grows.

Online resharding (adding/removing shards) works without downtime, though there is a brief performance dip during slot migration.


## 26. ElastiCache data tiering

### How it works

Data tiering extends ElastiCache storage by adding NVMe SSD to DRAM on r6gd node types. Keys always remain in memory. Values are tiered between DRAM (hot) and SSD (cold) using LRU. The advertised use case is workloads where ~20% of data is hot and accessed frequently.

Data tiering works best with values over 600 bytes. Below this threshold, keys consume a disproportionate share of RAM relative to values, and the SSD tier goes underutilised because RAM fills before SSD is meaningfully used.

### The 5% item-count threshold

When the percentage of values in memory drops below 5% of total values (by count), the service starts evicting data. This threshold:

- Is hard-coded and cannot be lowered without causing severe operational issues (confirmed by the data tiering service team)
- Uses item count, not memory bytes, as the trigger metric
- Exists to ensure the system retains enough values in DRAM for operational stability
- Has no roadmap for becoming configurable or switching to a byte-based metric (as of March 2026)

The 5% is the absolute floor. The service team considers 20% of values in memory the real target for the tiering model to work as intended.

### Eviction policies

Data tiering supports five eviction policies: `volatile-lru`, `allkeys-lru`, `volatile-lfu`, `allkeys-lfu`, and `noeviction`. With `noeviction`, new writes are blocked when the threshold is hit instead of evicting existing data.

There are only three ways to relieve memory pressure: evict data, prevent new writes (`noeviction`), or add memory (larger nodes). Reducing TTLs to lower overall data volume is the fourth option.

### When data tiering is a poor fit

Data tiering breaks down in two scenarios:

1. Small values (under 600 bytes). Keys always stay in memory. When values are small, keys fill RAM before SSD is meaningfully utilised. The customer pays for SSD capacity they can't use.

2. Highly skewed value sizes. When large and small values coexist, writing a large value to memory forces many small values to SSD (one item in, many items out). The item count in memory drops faster than the bytes freed would suggest. Retrieving those small values later creates SSD throughput pressure — high SSD read volume degrades overall system performance, not just latency.

In both cases, the correct response is usually to move away from data tiering to memory-only nodes (r7g). r7g nodes are often cheaper than r6gd nodes for the same usable DRAM, and eliminating the SSD tier removes the 5% threshold entirely.

### Monitoring: DatabaseMemoryUsagePercentage vs FreeableMemory

`DatabaseMemoryUsagePercentage` shows the percentage of DRAM allocated for customer data that is in use. `FreeableMemory` shows total host memory available, which includes memory reserved for fragmentation, replication, and I/O buffers — this memory is not available for customer data.

A cluster can show `FreeableMemory` > 0 whilst `DatabaseMemoryUsagePercentage` is at 100%. The customer data allocation is full even though the host has free memory. Use `DatabaseMemoryUsagePercentage` to assess whether the cluster is under memory pressure.

### reserved-memory-percent

The `reserved-memory-percent` parameter (default 25%, recommended up to 50% for write-heavy data tiering workloads) controls how much DRAM is reserved for non-data overhead. It does not affect the 5% item-count threshold. These are separate mechanisms.

### SSD throughput

SSD reads are not just a latency concern. If too much data is served from SSD, the entire system's throughput degrades. Workloads that push most values to SSD (because values are small or because large values displace many small ones) will hit throughput limits before they hit SSD capacity limits.

### r6gd node capacity (us-east-1, on-demand)

| Node type | DRAM | Usable DRAM (25% reserved) | SSD | On-demand $/hour |
|---|---|---|---|---|
| cache.r6gd.xlarge | ~26 GB | ~20 GB | ~118 GB | ~$0.79 |
| cache.r6gd.2xlarge | ~52 GB | ~39 GB | ~237 GB | ~$1.58 |
| cache.r6gd.4xlarge | ~105 GB | ~79 GB | ~473 GB | ~$3.16 |
| cache.r6gd.8xlarge | ~209 GB | ~157 GB | ~946 GB | ~$6.32 |

### Workarounds for the 5% threshold

1. Scale up (larger r6gd nodes): more DRAM means more values stay in memory, keeping the item-count ratio above 5%. Doesn't fix the root cause for small-value or skewed workloads.

2. Scale out (add shards): distributes items across more nodes so each node's ratio stays higher. Increases cost proportionally and doesn't eliminate the root cause.

3. Move to memory-only nodes (r7g): eliminates the SSD tier and the 5% threshold entirely. Often cheaper than r6gd for the same usable DRAM. No application changes required. This is the recommended path when data tiering is a poor fit.

4. Shorten TTLs: reduces total data volume, lowering memory pressure. Only viable if the application can tolerate shorter data lifetimes.

5. Normalise value sizes at the application layer: break large values into multiple smaller keys so item counts better reflect memory consumption. Requires application changes and increases key overhead (keys always stay in memory).

### MemoryDB data tiering

MemoryDB uses the same r6gd nodes and the same underlying engine. Whether the 5% item-count threshold applies to MemoryDB is unconfirmed (as of March 2026). Do not recommend MemoryDB data tiering as a workaround without confirmation from the MemoryDB service team. MemoryDB adds durability (multi-AZ transaction log) and incurs higher hourly node costs plus charges for data written to the cluster.

References:
- [Data tiering in ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/data-tiering.html)
- [ElastiCache for Valkey node type specific parameters](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ParameterGroups.Valkey.html)
- [ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/)
