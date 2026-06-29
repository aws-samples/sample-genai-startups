# Vector Database & AI Use Cases on AWS

Vector database selection, pgvector quantisation, Aurora vs OpenSearch Service for vector workloads.

**Glossary:** HNSW = Hierarchical Navigable Small World (a graph-based algorithm for approximate nearest neighbour search). halfvec = half-precision 16-bit float vector type in pgvector. QPS = Queries Per Second. Recall = the proportion of true nearest neighbours returned by an approximate search (1.0 = perfect). IVF = Inverted File Index (a partition-based vector index algorithm).


## 1. Vector database selection

### Decision tree

When selecting a vector database on AWS, follow this sequence:

1. If the customer already uses an AWS database with native vector search, recommend using it first. Test for recall, accuracy, performance, and scalability before introducing a new service.

2. If the current database doesn't support vectors, or testing reveals gaps, select based on primary data structure:
   - Structured/relational data: Aurora PostgreSQL or Amazon RDS for PostgreSQL with pgvector
   - Key-value pairs: DynamoDB + Amazon OpenSearch Service
   - Object data (PDFs, documents, audio, video): DocumentDB
   - JSON documents: DocumentDB
   - Graph data: Neptune Analytics
   - Other NoSQL with sub-10ms latency + durability: MemoryDB
   - Other NoSQL with sub-10ms latency, no durability: ElastiCache (Valkey 8.2+)
   - Low query volume (<100 QPS), latency tolerance >400ms: S3 with vector search
   - Advanced full-text search, hybrid search, cost-optimised: OpenSearch Service

3. If metadata exceeds 400KB per item: DynamoDB + OpenSearch Service.

4. If JOINs or ACID compliance required: pgvector on Aurora PostgreSQL or RDS for PostgreSQL.

5. If graph algorithms needed: Neptune Analytics.

6. OpenSearch Service is the general fallback for advanced search requirements.

### Scaling pgvector: access pattern determines the ceiling

The scalability limit of pgvector depends on whether queries are scoped or global:

**Scoped queries (per-user, per-tenant, per-device, per-time-window):**

Partition the table by the scoping key. Each partition contains a bounded subset of vectors (~1 GB or fewer). Within that partition, choose either:

- **Brute-force parallel scan**: 100% recall, zero index maintenance, higher latency (~200ms P50). Set `max_parallel_workers_per_gather = 16` to saturate EBS bandwidth. Best when perfect recall is non-negotiable and write volume is extreme.
- **Per-partition HNSW index**: high recall (0.95+), single-digit ms latency, but pays index build/maintenance cost on writes. Best for low-latency search within bounded partitions.

Both approaches scale to hundreds of billions of vectors because the query planner prunes to the relevant partition(s) first. The HNSW graph (if used) stays small per partition and fits in memory. As described in the AWS Database Blog case study, Ring runs 100–200 billion embeddings across Amazon RDS for PostgreSQL with pgvector using user-based partitioning, 4 clusters per region, halfvec storage, and brute-force scans — ingesting ~2 billion new embeddings per day with zero index maintenance.

**Global unscoped queries (search across all vectors from all users):**

Scaling depends on latency tolerance and concurrency:

*Low latency required (<10ms) — index must be memory-resident regardless of engine:*
- Up to ~50M vectors: Aurora pgvector with 3–5 read replicas
- 50M–500M vectors: Aurora pgvector with aggressive read replica scaling and halfvec quantisation
- Above 500M vectors: OpenSearch Service with sharding (10–30M vectors per shard), but still requires sufficient nodes to hold the index in RAM — the memory requirement doesn't disappear, it's distributed
- At 1B vectors x 1000-dim halfvec (~4.2 TB index): ~9 nodes with 512 GB RAM whether Aurora replicas or OpenSearch Service data nodes. The OpenSearch Service advantage is operational (native sharding, rebalancing, shard routing) not memory savings.
- Above 7.5 TB index: Aurora not viable for memory-resident <10ms queries (15 replicas x 512 GB max RAM). OpenSearch Service scales further by adding data nodes. However, if latency tolerance is relaxed (100–500ms), Aurora/RDS handles well beyond this via EBS-backed scans — see the Ring case study on the AWS Database Blog (150+ TB).

*Moderate latency acceptable (100–500ms) — EBS-backed scans viable:*
- Billions of vectors on Aurora/RDS pgvector without fitting the full index in RAM
- Use RDS Optimised Reads instances (r6id/r6gd with local NVMe) for additional caching tier
- Set `max_parallel_workers_per_gather` high (8–16) to saturate EBS throughput
- pg_prewarm for frequently accessed partitions/segments
- Concurrency is the constraint: each query consumes significant I/O bandwidth; at high QPS (thousands/sec) you need more clusters or move to OpenSearch Service

*Storage math (1000 dimensions, halfvec):*
- ~4.2 KB per vector (column + HNSW index entry)
- 1 billion vectors = ~4.2 TB
- Fits on 8–9 x r6id.8xlarge instances as read replicas (512 GB RAM each) if memory-resident required
- Fits on 2–3 instances if served from EBS/NVMe at 200–500ms latency

**Decision:** Ask three questions before recommending a scale ceiling: (1) Is the query scoped or global? (2) What latency is acceptable? (3) What concurrency (QPS) is expected?

### AWS databases with native vector search

- Amazon Aurora PostgreSQL (pgvector extension)
- Amazon RDS for PostgreSQL (pgvector extension)
- Amazon DocumentDB (native HNSW and IVF indexing)
- Amazon MemoryDB (native, sub-millisecond latency)
- Amazon ElastiCache Valkey 8.2+ (native, microsecond latency)
- Amazon OpenSearch Service (native)
- Amazon Neptune Analytics (native for graph)

### Encryption considerations

Vector embeddings may encode sensitive information from source data. All AWS database services listed above support encryption at rest (enabled by default on Aurora, RDS, DynamoDB, and MemoryDB). For encryption in transit, enforce TLS/SSL on all client connections — use `sslmode=require` for PostgreSQL, enable in-transit encryption in cluster configuration for MemoryDB/ElastiCache, and enable node-to-node encryption for OpenSearch Service domains. For compliance requirements, use customer-managed KMS keys instead of AWS-managed keys.

## 1b. pgvector quantisation types and recall impact

### Available types (pgvector 0.7.0+)

pgvector 0.7.0 introduced three quantised vector types:

- **halfvec**: half-precision 16-bit float. Indexing up to 4,000 dimensions.
- **bit**: binary quantisation (1 bit per dimension). Indexing up to 64,000 dimensions. Supports Hamming and Jaccard distance functions.
- **sparsevec**: sparse vectors, indexing up to 1,000 non-zero dimensions.

Available on Amazon RDS for PostgreSQL since May 2024 (16.3, 15.7, 14.12, 13.15) and Aurora PostgreSQL since August 2024. Latest version is pgvector 0.8.0 (April 2025 on Aurora), which added iterative index scans and HNSW performance improvements — quantisation types came in 0.7.0.

### Recall benchmarks (AWS Database Blog, Aurora r7g.12xlarge)

**Scalar quantisation (halfvec — 16-bit float):**

| Dataset | Dimensions | fullvec recall | halfvec recall | Index size reduction |
|---|---|---|---|---|
| Cohere 10M | 768 | 0.950 | 0.950 | 50% |
| OpenAI 5M | 1536 | 0.971 | 0.969 | 50% |

Recall is essentially unchanged. halfvec is a free win — 50% storage and memory savings with no measurable recall loss.

**Binary quantisation (1-bit per dimension, with re-ranking):**

| Dataset | Dimensions | fullvec recall | binary recall (with re-rank) | Index build speedup |
|---|---|---|---|---|
| OpenAI 5M | 1536 | 0.973 | 0.822 | 67x |
| Cohere 10M | 768 | 0.934 | 0.659 | 67x |

Binary quantisation hits recall hard. The 768-dimension dataset drops to 0.659 — unusable for most production workloads. The 1536-dimension dataset fares better at 0.822 but is still a significant degradation. Higher dimensionality helps because more information survives the 1-bit compression. Binary quantisation is useful for fast initial filtering with a re-ranking step, not as a standalone index.

### No native int8 (8-bit) quantisation in pgvector

pgvector does not have a native int8 vector type. The jump goes from halfvec (16-bit) to bit (1-bit). There is no open issue or roadmap item for int8 support. The pgvector maintainer has kept the extension lean — halfvec and bit cover the two ends of the spectrum, and anything in between requires a fundamentally different approach (scalar quantisation with range mapping, or product quantisation with codebooks) which adds complexity to the index build and query path.

**Alternatives for int8/product quantisation:**

- **Lantern** ([github.com/lanterndata/lantern](https://github.com/lanterndata/lantern)): PostgreSQL extension that implements product quantisation with an 8-bit unsigned integer encoding (`PQVEC` type). Each subvector dimension is encoded as a centroid ID (0–255). PostgreSQL lacks a native 1-byte integer type, so Lantern created a custom type. Benchmarks on 100M 768-dimensional vectors (LAION2B): 0.71 recall@10 without re-ranking (50ms), 0.90 recall@10 with re-ranking over top 40 (73ms). 6x memory reduction for the index. Not an AWS-managed service.
- **OpenSearch Service**: supports byte quantisation (8-bit integer) natively with its FAISS engine, plus FP16, binary, and product quantisation. If a customer needs int8 and is already considering OpenSearch Service, this is the managed path.

### Recommendation

- **halfvec**: use it by default. No recall cost, 50% storage savings.
- **Binary quantisation**: use only as a pre-filter with re-ranking against full-precision vectors. Test recall with your dataset — it is dimension-dependent and can be severe at lower dimensions.
- **int8/product quantisation**: not available in pgvector. Consider OpenSearch Service (managed) or Lantern (self-managed PostgreSQL extension) if needed.

References:
- [Load vector embeddings up to 67x faster with pgvector and Amazon Aurora](https://aws.amazon.com/blogs/database/load-vector-embeddings-up-to-67x-faster-with-pgvector-and-amazon-aurora/)
- [pgvector 0.7.0 Released — PostgreSQL](https://www.postgresql.org/about/news/pgvector-070-released-2852/)
- [Announcing pgvector 0.8.0 support in Aurora PostgreSQL](https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql/)
- [Supercharging vector search with pgvector 0.8.0 on Aurora PostgreSQL](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)
- [Product Quantization in Postgres — Lantern](https://lantern.dev/blog/pq)
- [OpenSearch Service quantization techniques](https://aws.amazon.com/blogs/big-data/cost-optimized-vector-database-introduction-to-amazon-opensearch-service-quantization-techniques/)


## 2. Aurora PostgreSQL vs OpenSearch Service for vector workloads

### Working set sizing

The 80/20 rule applies to HNSW vector indexes: 80% of queries hit 20% of the data. Only 20% of the index needs caching to achieve 80%+ hit ratios because:

- Higher HNSW graph layers (used for initial search) are small and frequently accessed
- Query locality follows a power law distribution
- Graph traversal creates predictable access patterns

Realistic memory requirements at 20% working set:

| Full index size | Working set (20%) | Total RAM needed |
|-----------------|-------------------|------------------|
| 10 GB | 2 GB | 8 GB |
| 100 GB | 20 GB | 32 GB |
| 1 TB | 200 GB | 256 GB |
| 10 TB | 2 TB | 2.5 TB |

RAM figures include buffer for connections, query processing, and other operations.

### Cost break-even

Cost parity between Aurora PostgreSQL and OpenSearch Service occurs around 75-100 GB index size.

- Below 50 GB: Aurora wins on cost and simplicity
- 50-100 GB: Roughly equivalent
- Above 100 GB: OpenSearch Service wins on cost efficiency
- Above 7.5 TB: Aurora not viable (15 replicas x 512 GB max RAM)

### When to choose Aurora PostgreSQL with pgvector

- Queries are scoped to a partition (per-user, per-tenant, per-device) — scales to hundreds of billions regardless of index strategy
- Global search with index size under 100 GB
- PostgreSQL is already the system of record
- Workload is primarily transactional with some vector search
- Team has limited search infrastructure experience
- ACID guarantees needed for vector updates
- Sub-100ms replication lag required
- Perfect recall required (use partitioned brute-force scans)

### When to choose OpenSearch Service

- Global unscoped search with index size above 100 GB
- Search is the primary workload
- Need to scale global search beyond 500M vectors
- Advanced search features required (faceting, aggregations, hybrid search)
- Team has search infrastructure expertise
- Need byte quantisation (int8), product quantisation, or hybrid keyword+vector search

### Incremental cost: adding vectors to existing OpenSearch Service

For customers already running OpenSearch Service for product catalogue, adding vector search to the existing cluster avoids the fixed cost of a new Aurora PostgreSQL cluster (writer + reader instances). Actual savings depend on whether existing nodes have spare RAM and storage headroom — if no node upgrade is needed, the incremental cost is storage only. Run your own comparison using the pricing pages linked below.

### Cost optimisation strategies

Aurora PostgreSQL:
- Reserved Instances: 35% (1-year), 52% (3-year) discount
- Monitor buffer cache hit ratio; scale down if consistently below 80% memory utilisation
- Use Aurora I/O-Optimised for high-throughput workloads
- Aurora Optimised Reads extends cache to local NVMe (up to 5x memory capacity)

OpenSearch Service:
- Reserved Instances: 35% (1-year), 52% (3-year) discount
- Target 10-30M vectors per shard
- UltraWarm for cold data: $0.024/GB-month vs $0.135/GB-month (82% storage reduction)
- Consider OpenSearch Serverless for variable workloads

References:
- [Ring's billion-scale semantic video search with Amazon RDS for PostgreSQL and pgvector (AWS Database Blog)](https://aws.amazon.com/blogs/database/rings-billion-scale-semantic-video-search-with-amazon-rds-for-postgresql-and-pgvector/)
- [Amazon Aurora Pricing](https://aws.amazon.com/rds/aurora/pricing/)
- [Amazon OpenSearch Service Pricing](https://aws.amazon.com/opensearch-service/pricing/)
- [Aurora PostgreSQL cluster cache management](https://aws.amazon.com/blogs/database/introduction-to-aurora-postgresql-cluster-cache-management/)
- [Accelerate HNSW indexing with pgvector on Aurora](https://aws.amazon.com/blogs/database/accelerate-hnsw-indexing-and-searching-with-pgvector-on-amazon-aurora-postgresql-compatible-edition-and-amazon-rds-for-postgresql/)
- [Build billion-scale vector databases with GPU acceleration on Amazon OpenSearch Service](https://aws.amazon.com/blogs/big-data/build-billion-scale-vector-databases-in-under-an-hour-with-gpu-acceleration-on-amazon-opensearch-service/)
