# PostgreSQL Performance, Monitoring & Operations

pg_stat_statements, Performance Insights, index management, table partitioning, JSONB/GIN indexes, schema change management, time-series patterns, CDC/logical replication.

**Glossary:** AAS = Average Active Sessions. CDC = Change Data Capture (streaming database changes to external systems). GIN = Generalised Inverted Index (PostgreSQL index type for JSONB and full-text search). MVCC = Multi-Version Concurrency Control. TPS = Transactions Per Second. WAL = Write-Ahead Log (PostgreSQL's mechanism for durability and replication).


## 11. PostgreSQL performance analysis and query monitoring

### pg_stat_statements

The `pg_stat_statements` extension tracks execution statistics for all SQL statements. It helps identify slow queries and resource-heavy operations. Enable by adding to `shared_preload_libraries` parameter (requires instance reboot).

```sql
SELECT query, calls, total_exec_time, mean_exec_time, rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Default `pg_stat_statements.max` is 5000. For high-volume environments, increase to 50000-100000 to capture more unique queries before eviction. Monitor `pg_stat_statements_info.dealloc` to detect evictions — if this value is zero, no statements have been missed.

### Performance Insights

Identifies top SQL queries consuming resources and visualises wait events. Free tier: 7 days of performance data history and 1M API requests/month.

Key metrics in the Top SQL tab:
- Executions/sec
- Rows/exec
- Latency
- Load (AAS - Average Active Sessions)

Red flags in EXPLAIN output:
- Seq Scan on large tables
- High cost estimates
- Large difference between estimated and actual rows
- High buffer reads (disk I/O)
- Nested loops with large datasets

### Cache hit ratio monitoring

Aurora provides native `BufferCacheHitRatio` CloudWatch metric. RDS PostgreSQL does not.

For RDS PostgreSQL, query `pg_stat_database`:

```sql
SELECT
  datname,
  ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) AS cache_hit_ratio
FROM pg_stat_database
WHERE datname NOT IN ('template0', 'template1', 'rdsadmin');
```

### Query monitoring at scale (200K+ TPS)

All database-level logging approaches carry risk at high TPS:

- Network bandwidth shared between Aurora cluster storage and local instance storage
- Log disk overflow causes instance/replica instability
- Monitor with CloudWatch metric: `FreeLocalStorage`

**pgaudit log volume risks:**

The Aurora log volume is separate from the temp storage volume. The temp storage rule of 2x memory and the `FreeLocalStorage` CloudWatch metric do not apply to the log volume. Specific risks:

- No documentation on the size of the log volume
- No CloudWatch metric to monitor log volume usage
- When the log volume fills, the instance may crash
- The log volume is not cleared on reboot
- Storage bandwidth exhaustion possible with high log traffic

Because of these risks, full pgaudit logging should be avoided. Use targeted pgaudit logging only on specific tables not captured through pg_stat_statements sampling. Exclude frequently used tables to reduce overhead.

**Recommended approach: pg_stat_statements sampling**

Use pg_stat_statements as the primary method with `pg_stat_statements.max` set to 50000-100000. Sample frequently to catch rare queries before eviction. Coverage depends on workload diversity — the module evicts least-executed statements when `pg_stat_statements.max` is reached, so high-cardinality workloads may lose rare queries. Monitor the `dealloc` counter in `pg_stat_statements_info` to detect eviction. Overhead is minimal (shared memory proportional to max entries) unless `track_planning` is enabled on high-concurrency workloads.

For remaining edge cases, use targeted pgaudit logging only on specific tables not captured through sampling. This will not capture rare queries on frequently used tables.

**Alternative: 100% coverage without database logging**

If 100% query coverage is required, application-level logging bypasses database logging entirely and avoids the infrastructure risks:

1. Database driver/connection pool wrapper: Intercept at JDBC/psycopg2/node-postgres layer, send to Kinesis/S3/Kafka async
2. ORM instrumentation: Hook into query execution (Hibernate/SQLAlchemy/Sequelize)
3. Database proxy on application side: pgbouncer/pgpool with query logging to external system
4. Sidecar logging container: Network-level capture in containerised environments

**VPC Traffic Mirroring**

Copies network traffic from Aurora ENI to monitoring appliance. Zero database impact. Parse PostgreSQL wire protocol to extract queries.

Requirements:
- Unencrypted database connections (TLS traffic cannot be inspected)
- Packet processing infrastructure (pgShark, Wireshark with PostgreSQL dissector)

If connections are encrypted, a TLS terminating proxy (Imperva SecureSphere, DataSunrise) can sit inline, but becomes a critical path component.

References:
- [pg_stat_statements for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_PerfInsights.UsingDashboard.AnalyzeDBLoad.AdditionalMetrics.PostgreSQL.html)
- [aurora_stat_statements function](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora_stat_statements.html)
- [Using pgAudit](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.pgaudit.html)
- [Performance Insights](https://docs.aws.amazon.com/prescriptive-guidance/latest/amazon-rds-monitoring-alerting/performance-insights-tools.html)
- [Analysing queries with Top SQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_PerfInsights.UsingDashboard.AnalyzeDBLoad.AdditionalMetrics.html)
- [Troubleshoot local storage issues in Aurora PostgreSQL](https://aws.amazon.com/premiumsupport/knowledge-center/postgresql-aurora-storage-issue/)


## 12. Index management

### Creating indexes without blocking

Standard `CREATE INDEX` acquires an exclusive lock, blocking all writes. Use `CREATE INDEX CONCURRENTLY` for production:

```sql
CREATE INDEX CONCURRENTLY idx_name ON table_name(column_name);
```

Characteristics:
- Allows concurrent reads and writes
- Takes 2-3x longer than standard CREATE INDEX
- Cannot run inside a transaction block
- Can fail if concurrent updates conflict; failed indexes marked INVALID

Monitor progress (PostgreSQL 12+):
```sql
SELECT phase,
       round(100.0 * blocks_done / nullif(blocks_total, 0), 1) AS "% complete"
FROM pg_stat_progress_create_index;
```

### Detecting unused indexes

```sql
SELECT schemaname, tablename, indexname, idx_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelname NOT LIKE 'pg_toast%'
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Rebuilding bloated indexes

```sql
REINDEX INDEX CONCURRENTLY idx_name;
```

Or create new and drop old:
```sql
CREATE INDEX CONCURRENTLY idx_name_new ON table_name(column_name);
DROP INDEX CONCURRENTLY idx_name;
ALTER INDEX idx_name_new RENAME TO idx_name;
```

Find invalid indexes:
```sql
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE indexdef LIKE '%INVALID%';
```

References:
- [Rebuilding indexes - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/postgresql-maintenance-rds-aurora/reindex.html)


## 13. Table partitioning

### Range partitioning by month

```sql
CREATE TABLE audit_log (
    id BIGSERIAL,
    created_at TIMESTAMP NOT NULL,
    -- other columns
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_log_2026_01 PARTITION OF audit_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;
```

Partition key must be part of primary key or unique constraints.

### Automated management with pg_partman

```sql
CREATE SCHEMA partman;
CREATE EXTENSION pg_partman SCHEMA partman;

SELECT partman.create_parent(
    p_parent_table := 'public.audit_log',
    p_control := 'created_at',
    p_type := 'native',
    p_interval := '1 month',
    p_premake := 3,
    p_start_partition := '2026-01-01'
);
```

Schedule maintenance with pg_cron:
```sql
CREATE EXTENSION pg_cron;
SELECT cron.schedule('partition-maintenance', '0 3 * * *',
    $$SELECT partman.run_maintenance_proc()$$);
```

Configure retention:
```sql
UPDATE partman.part_config
SET retention = '12 months',
    retention_keep_table = false,
    retention_keep_index = false
WHERE parent_table = 'public.audit_log';
```

### Benefits

- Significantly faster queries through partition pruning (improvement depends on partition count and selectivity — queries touching one partition out of hundreds avoid scanning the rest entirely)
- Reduced buffer cache pressure (only current partition indexes in memory)
- Efficient data retention (drop old partitions instead of DELETE)
- Smaller working set per partition

Verify partition pruning:
```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM audit_log
WHERE created_at >= '2026-02-01' AND created_at < '2026-03-01';
-- Look for "Partitions pruned: X"
```

References:
- [PostgreSQL table partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Managing partitions with pg_partman](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL_Partitions.html)


## 15. JSONB with GIN indexes

For schema-flexible columns within PostgreSQL:

```sql
CREATE TABLE features (
    id SERIAL PRIMARY KEY,
    metadata JSONB
);

-- Default GIN index
CREATE INDEX idx_metadata ON features USING GIN (metadata);

-- jsonb_path_ops for better containment query performance
CREATE INDEX idx_metadata_path ON features USING GIN (metadata jsonb_path_ops);
```

Querying:
```sql
-- Containment (uses GIN index)
SELECT * FROM features WHERE metadata @> '{"status": "active"}';

-- Key existence
SELECT * FROM features WHERE metadata ? 'priority';

-- Nested attributes
SELECT metadata->'user'->>'name' FROM features
WHERE metadata @> '{"user": {"role": "admin"}}';
```

`jsonb_path_ops` is smaller and faster for containment queries but doesn't support key existence operators (`?`, `?|`, `?&`).

Trade-off: GIN index updates are more expensive than standard B-tree indexes for write operations.

References:
- [PostgreSQL JSONB data type](https://www.postgresql.org/docs/current/datatype-json.html)
- [JSONB indexing with GIN](https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING)


## 16. Schema change management with Liquibase

Liquibase provides database-independent schema change management with version control integration.

Relevant capabilities:
- Procedural code management: Handles triggers, stored procedures, and functions using `runOnChange="true"` flag
- FDW lifecycle management: Version-controls FDW definitions as changesets
- Change detection: Automatically detects modifications and re-applies changed procedures
- Rollback support
- CI/CD integration

The `runOnChange="true"` flag allows modification of triggers, procedures, and FDW definitions without creating new migration files each time.

References:
- [Deploy, track, and roll back RDS database code changes using Liquibase and Jenkins](https://aws.amazon.com/blogs/opensource/rds-code-change-deployment/)
- [Integrate Amazon RDS schema changes into CI/CD pipelines with GitLab and Liquibase](https://aws.amazon.com/blogs/apn/how-to-integrate-amazon-rds-schema-changes-into-ci-cd-pipelines-with-gitlab-and-liquibase/)
- [Liquibase removes database bottlenecks](https://aws.amazon.com/blogs/awsmarketplace/liquibase-removes-database-bottlenecks-for-faster-safer-database-releases/)


## 30. Aurora PostgreSQL analytics offload

### Recommended: Aurora zero-ETL integration with Amazon Redshift

Aurora zero-ETL is a fully managed integration that replicates transactional data from Aurora PostgreSQL to Amazon Redshift in near real-time — no pipelines, no CDC infrastructure, no logical replication slots to manage. AWS handles the replication automatically.

**Requirements:**
- Aurora PostgreSQL 16.4+ or 17.4+
- Source and target must be in the same Region
- All replicated tables must have primary keys
- Source cannot use Aurora Limitless Database
- Requires `aurora.enhanced_logical_replication=1` parameter (set automatically if you let RDS configure during integration creation). This writes all column values to WAL, which may increase IOPS on the source

**Setup:**
1. Create a custom DB cluster parameter group with zero-ETL settings enabled
2. Create an Amazon Redshift Serverless workgroup (or provisioned cluster) as the target
3. Create the zero-ETL integration in the RDS console — specify the Aurora cluster as source, Redshift as target
4. Define data filter patterns (at minimum: `{database-name}.*.*`)
5. Data is available in Redshift within minutes — no ETL code to write or maintain

**Architecture pattern:** Aurora PostgreSQL as the OLTP write-path; Redshift as the analytics/reporting layer. Zero-ETL eliminates the need to build and maintain separate CDC pipelines for append-heavy workloads (IoT readings, metering data, activity logs). Shorten PostgreSQL retention (e.g. 3 months via partition drops) and let Redshift hold the full history.

**Limitations:**
- Source and target must be in the same Region (cross-region not supported)
- DDL changes on source tables can trigger a table resync (table unavailable for querying during resync)
- Two-phase transactions not supported
- If the source is the primary in an Aurora Global Database and fails over, the integration becomes inactive — must delete and recreate
- Some data types not replicated (see AWS docs for the mapping table)

References:
- [Aurora zero-ETL integrations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/zero-etl.html)
- [Supported Regions and Aurora DB engines for zero-ETL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.Zero-ETL.html)
- [Creating Aurora zero-ETL integrations with Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/mgmt/zero-etl-setting-up.create-integration-aurora.html)

### Alternative: Logical replication to external analytics stores

If zero-ETL doesn't fit (e.g., target is not Redshift, cross-region needed, or Aurora version < 16.4), use PostgreSQL logical replication to stream changes to an external analytics store.

**Aurora PostgreSQL setup for logical replication:**
1. Set `rds.logical_replication = 1` in the cluster parameter group (requires reboot)
2. Configure `max_replication_slots` and `max_wal_senders` (defaults may be sufficient; increase if running multiple CDC consumers)
3. Grant the `rds_replication` role to the CDC user
4. CDC consumer connects to the Aurora writer endpoint (logical replication requires write access to create and manage replication slots)

**Aurora Global Database compatibility:** Logical replication works on Aurora Global Database writers. Connect to the primary region's writer endpoint. Logical replication operates at the PostgreSQL engine level (WAL streaming), while Global Database's cross-region replication operates at the storage layer — the two mechanisms are independent and coexist.

**WAL management:** Monitor `max_slot_wal_keep_size` to prevent WAL accumulation if the CDC consumer falls behind. A stalled replication slot prevents WAL cleanup, which can fill storage. Set `max_slot_wal_keep_size` to a reasonable limit (e.g. 100GB) so Aurora drops the slot rather than running out of storage.

**If you are already using ClickHouse:** ClickPipes (GA May 2025) is ClickHouse's native CDC connector for PostgreSQL, powered by PeerDB. It uses the same logical replication infrastructure described above. See the [ClickPipes Aurora PostgreSQL source setup guide](https://clickhouse.com/docs/en/integrations/clickpipes/postgres/source/aurora) for configuration.

References:
- [Setting up logical replication for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.Configure.html)
- [Using pglogical to synchronise data across instances — Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.pglogical.html)


## 33. Time-series data in PostgreSQL with partitioning

### Capacity planning

For append-heavy time-series workloads (IoT readings, metering data, sensor data), estimate annual row volume:

```
devices × readings_per_day × 365 = rows/year
```

Example: 200K devices with half-hourly readings = 200,000 × 48 × 365 = ~3.5 billion rows/year.

### PostgreSQL as write-path with analytics offload

PostgreSQL handles billions of rows with range partitioning (by month via pg_partman). Partition pruning skips irrelevant partitions entirely, so queries on recent data only scan the matching partition rather than the full table. Old partitions can be dropped cleanly for retention.

For long-term analytics, offload to Amazon Redshift via zero-ETL integration (Aurora PostgreSQL 16.4+, fully managed, no pipeline code) or via logical replication for other targets. PostgreSQL becomes the write-path and short-term query store; the analytics layer holds the full history.

If PostgreSQL partitioning starts struggling (query planning overhead with hundreds of partitions, vacuum pressure at billions of rows per region), shorten retention in PostgreSQL (e.g. keep 3 months) rather than introducing a separate time-series database. The analytics layer already holds the full history.

### When to consider a dedicated time-series database

- Sub-second aggregation queries across years of data at the source (not offloaded to analytics)
- Downsampling and retention policies more complex than "drop old partitions"
- Native time-series functions (gap filling, interpolation, moving averages) needed at the database layer
- Write throughput exceeds what a single Aurora cluster can handle (hundreds of thousands of inserts per second sustained)


## 35. PostgreSQL logical replication for CDC

### Physical vs logical replication

PostgreSQL has two replication modes. The primary key requirement only applies to one of them.

Physical (streaming) replication operates at the WAL byte level. The primary ships write-ahead log records; the standby replays them as a block-level copy. No schema awareness, no primary key requirement. Everything replicates: tables (with or without primary keys), indexes, sequences, DDL changes. The standby is a byte-for-byte copy of the primary. Aurora read replicas, RDS Multi-AZ standbys, and RDS Multi-AZ cluster readers all use physical replication for HA.

Logical replication decodes WAL into logical change events (INSERT, UPDATE, DELETE) using PostgreSQL's logical decoding framework (built into core since version 10). The source creates a publication; each consumer connects via a subscription and receives changes through the `pgoutput` output plugin.

| | Physical replication (HA) | Logical replication (CDC) |
|---|---|---|
| Primary key required | No | Yes, for UPDATEs/DELETEs |
| DDL replicated | Yes (byte-level) | No |
| Sequences replicated | Yes (byte-level) | No |
| Use case | Failover, read replicas | CDC to external systems |

### Connection model

The subscriber initiates the connection. When a subscription is created, PostgreSQL spawns a WAL sender process on the source that reads the WAL, applies the publication's filters in memory, and pushes matching changes over the connection. Each subscriber gets its own WAL sender process and its own replication slot.

The source bears the heavier load: WAL decoding and filtering are CPU-bound, proportional to write volume on published tables. Each logical replication subscriber runs a separate WAL sender process. Multiple consumers compound the load.

Note: Aurora zero-ETL integrations with Redshift use an enhanced version of logical replication (`aurora.enhanced_logical_replication=1`). This is fully managed — AWS handles replication slot lifecycle — but it does consume WAL resources on the source. The key advantage is zero pipeline code and automatic schema propagation.

Reference: [PostgreSQL Logical Replication Architecture](https://www.postgresql.org/docs/current/logical-replication-architecture.html)

### Primary key requirement

Without a primary key or `REPLICA IDENTITY FULL` set on the table, PostgreSQL cannot identify which row to update or delete on the subscriber. UPDATEs and DELETEs fail. INSERTs work without a primary key.

`REPLICA IDENTITY FULL` uses the entire row as the identifier. Performance implications: more data logged per change, faster WAL growth — particularly for tables with frequent updates or deletes and wide rows.

Reference: [PostgreSQL ALTER TABLE — REPLICA IDENTITY](https://www.postgresql.org/docs/current/sql-altertable.html)

### Enabling on Aurora PostgreSQL

Set `rds.logical_replication = 1` in the cluster parameter group (requires reboot). Configure `max_replication_slots` and `max_wal_senders` if running multiple CDC consumers.

Reference: [Setting up logical replication for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.Configure.html)

### Operational constraints

DDL changes are not replicated. If the source adds a column, subscribers must `ALTER TABLE` independently.

Sequences are not replicated. Subscribers that insert rows locally need separate sequence ranges or UUIDs.

Replication slot WAL retention: if a subscriber goes offline, WAL accumulates on the source indefinitely. Set `max_slot_wal_keep_size` to cap retention and prevent storage exhaustion. Monitor via `pg_replication_slots`:

```sql
SELECT slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
FROM pg_replication_slots
WHERE slot_type = 'logical';
```

Schema change backfills generate WAL storms. A bulk `UPDATE` across a published table (e.g. backfilling a new column on 200K rows) generates 200K WAL records that flow through to every subscriber. Replication lag spikes during the backfill. Mitigation: apply DDL on subscribers first, then backfill on the source during low-traffic periods.

References:
- [PostgreSQL Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html)
- [PostgreSQL pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html)

### Column and row filtering (PostgreSQL 15+)

PostgreSQL 15+ supports column-level and row-level filtering within publications. The source sends only specific columns and rows matching a WHERE clause, reducing WAL decoding overhead and network transfer to subscribers.

```sql
CREATE PUBLICATION my_pub FOR TABLE orders (id, status, amount)
    WHERE (status = 'completed');
```

Reference: [PostgreSQL logical replication: How to replicate only the data that you need — AWS Database Blog](https://aws.amazon.com/blogs/database/postgresql-logical-replication-how-to-replicate-only-the-data-that-you-need/)
