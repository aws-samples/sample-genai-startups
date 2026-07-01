# Database Decoupling & Integration Patterns

Foreign Data Wrappers, API abstraction, event-driven sync, Aurora DSQL limitations, RDS storage internals.

**Glossary:** ACID = Atomicity, Consistency, Isolation, Durability (database transaction guarantees). CDC = Change Data Capture. CRUD = Create, Read, Update, Delete. FDW = Foreign Data Wrapper (PostgreSQL extension for querying remote databases). FK = Foreign Key. IOPS = Input/Output Operations Per Second. PL/pgSQL = PostgreSQL's built-in procedural language for stored functions. RAID 0 = disk striping without redundancy (performance optimisation). WAL = Write-Ahead Log.


## 14. Database decoupling patterns

### Foreign Data Wrappers (FDWs) - short-term

Remote tables accessed as if local using PostgreSQL's `postgres_fdw` extension. Each microservice database maintains an independent cache.

Best for:
- 5 or fewer shared tables
- Reference data with infrequent updates
- Short-term solution whilst building API layer

Disadvantages:
- Creates technical debt if overused
- Requires lifecycle management of FDW definitions
- Still increases load on primary database

Use materialised views for reference data that updates infrequently.

References:
- [Foreign data wrappers for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.foreign-data-wrappers.html)
- [Using postgres_fdw](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/postgresql-commondbatasks-fdw.html)
- [Federated query support for Aurora PostgreSQL and RDS for PostgreSQL](https://aws.amazon.com/blogs/database/federated-query-support-for-amazon-aurora-postgresql-and-amazon-rds-for-postgresql/)
- [Materialised views](https://www.postgresql.org/docs/current/rules-materializedviews.html)

### API abstraction layer - long-term

Expose common access patterns as immutable API contracts. Applications consume via API rather than direct database access.

The API itself requires a backing datastore and caching layer. The underlying data must still be propagated using FDWs, event-driven synchronisation, or scheduled replication. The API provides value by standardising access patterns and enabling future flexibility, but operational overhead of data synchronisation remains.

### Event-driven synchronisation - scalable

Applications publish changes to event bus (Kafka, Kinesis, or SQS). Subscribers replicate to domain databases.

Trigger-based alternative: Lambda functions triggered on table updates using PostgreSQL's `aws_lambda` extension.

References:
- [Invoking Lambda from Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/PostgreSQL-Lambda.html)
- [Lambda function and parameter reference](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/PostgreSQL-Lambda-functions.html)


## 29. Aurora DSQL limitations

Aurora DSQL is AWS's distributed, serverless PostgreSQL-compatible database designed for multi-region active-active writes. It has significant limitations compared to standard Aurora PostgreSQL.

### Missing features

- No PostgreSQL logical replication (WAL streaming). Zero-ETL integrations and any CDC tool that relies on PostgreSQL logical replication (pglogical or other subscribers) will not work.
- **Native CDC available (public preview):** DSQL has its own CDC mechanism that captures row-level changes and publishes them to Amazon Kinesis Data Streams. It operates at the storage layer (not WAL-based), captures all tables (no selective filtering), and delivers events with at-least-once semantics. Target: Kinesis only. Limitations: unordered delivery, INSERT/UPDATE indistinguishable (both `op: "c"` — `"u"` planned for GA), DELETE events contain only the primary key. Multi-region: a CDC stream captures committed writes from all regions regardless of where the stream is created. See [Getting started with CDC in Aurora DSQL](https://aws.amazon.com/blogs/database/getting-started-with-change-data-capture-in-amazon-aurora-dsql/).
- No foreign key constraints. `FOREIGN KEY` and `REFERENCES` are absent from the grammar.
- No PL/pgSQL.
- No temporary tables.
- No `TRUNCATE`.
- No extensions — no pgvector, no pg_partman, no pg_cron, no postgres_fdw.
- 1-hour connection timeout.

### Transaction limits

3,000 rows per transaction. Bulk imports require chunking.

### When DSQL is appropriate

Multi-region active-active writes where the application can tolerate the above restrictions: simple CRUD operations with no FK constraints, no stored procedures, no CDC requirements, and small transaction sizes.

### When DSQL is not appropriate

- Any workload requiring CDC/logical replication to downstream systems
- Applications relying on FK constraints for data integrity
- Workloads using PL/pgSQL, extensions, or temporary tables
- Bulk data loading (3,000-row limit per transaction)

References:
- [Aurora DSQL — CREATE TABLE supported syntax](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/create-table-syntax-support.html)
- [Aurora DSQL — supported SQL features](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-supported-sql-features.html)
- [Aurora DSQL — considerations](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/considerations.html)
- [Aurora DSQL — migrating from PostgreSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-migration-guide.html)


## 36. RDS storage internals

### EBS volume striping

RDS automatically stripes across multiple EBS volumes in a RAID 0 configuration for performance. The number of volumes depends on storage size and engine:

| Database engine | Storage size | EBS volumes |
|---|---|---|
| Db2, MariaDB, MySQL, PostgreSQL | < 400 GiB | 1 |
| Db2, MariaDB, MySQL, PostgreSQL | 400–65,536 GiB | 4 |
| Oracle | < 200 GiB | 1 |
| Oracle | 200–65,536 GiB | 4 |
| SQL Server | Any | 1 |

Crossing the threshold (e.g. < 400 GiB to >= 400 GiB for PostgreSQL) triggers an I/O-intensive storage modification: RDS provisions four new volumes and transparently migrates data from the single volume. This can take several hours and consume significant IOPS while the instance remains in the `Modifying` state.

References:
- [Amazon RDS DB instance storage](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Storage.html)
- [I/O-intensive storage modifications](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIOPS.IOIntensive.html)

### GP2 to GP3 migration

GP2 to GP3 is an online operation with no downtime. The RDS instance enters `storage-optimization` status during the conversion, which can take several hours. Elevated latencies (single-digit milliseconds) may occur during this period. A 6-hour cooldown applies before further storage modifications.

GP3 introduces independently provisionable throughput, which GP2 did not expose. The default throughput values differ:

| Volume type | Throughput |
|-------------|-----------|
| GP2 (>= 334 GiB) | 250 MiB/s (fixed maximum) |
| GP2 (170-333 GiB) | Up to 250 MiB/s (burst) |
| GP2 (<= 170 GiB) | 128 MiB/s (fixed maximum) |
| GP3 (default) | 125 MiB/s |
| GP3 (provisionable) | Up to 2,000 MiB/s |

Customers migrating from GP2 volumes >= 334 GiB who do not explicitly set GP3 throughput will experience a 50% throughput reduction (250 MiB/s to 125 MiB/s).

SQL Server is disproportionately affected because it uses a single EBS volume (see striping table above). Other engines with 4-volume RAID 0 still have 500 MiB/s aggregate throughput at GP3 defaults. SQL Server lands at 125 MiB/s on a single volume — a floor where commit latency becomes visible because transaction log writes are sequential and throughput-bound.

Recommended steps:

1. Record current GP2 volume size, baseline IOPS, and throughput (use CloudWatch `VolumeReadBytes` + `VolumeWriteBytes` to measure actual throughput usage)
2. When modifying to GP3, explicitly set throughput to match or exceed the GP2 baseline (250 MiB/s for volumes >= 334 GiB)
3. Set IOPS to at least 3,000 (GP3 baseline) or match the GP2 baseline (`volume size in GiB x 3`, capped at 16,000)
4. Test on a snapshot-restored instance first if the workload is latency-sensitive
5. Monitor `WriteLatency` and `ReadLatency` CloudWatch metrics after migration

GP3 throughput pricing: baseline 125 MiB/s is included. Additional throughput costs $0.04/provisioned MiB/s-month. Provisioning 250 MiB/s adds $5/month (125 MiB/s additional x $0.04).

SQL Server supports up to 3 additional volumes on `H:`, `I:`, `J:` (explicitly configured, not striped). Each additional volume has its own independent throughput setting — ensure all volumes are configured appropriately during migration.

References:
- [Amazon EBS General Purpose SSD volumes](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [Modifying settings for General Purpose SSD (gp3) storage - Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIOPS.gp3.html)
- [Configure additional storage volumes with Amazon RDS for SQL Server](https://aws.amazon.com/blogs/database/configure-additional-storage-volumes-with-amazon-rds-for-sql-server/)

### Multi-AZ instance block-level replication

RDS Multi-AZ instance deployments use a replication layer installed between the database application and the EBS volumes. This layer intercepts all I/O requests and synchronously replicates writes to a standby instance's EBS volumes in a different AZ. The database has no awareness of this replication — it operates below the filesystem.

The replication layer tracks modified blocks during disconnection events for fast resynchronisation. The standby cannot serve read traffic because the replication layer does not allow mounting the filesystem in read-only mode while replicating.

This is distinct from Aurora's architecture, where storage is a shared distributed layer across 6 storage nodes. In RDS, each instance has its own independent EBS volumes, and the block-level replication layer bridges them.

For Multi-AZ instance deployments, the block-level replication sits on top of the LVM/RAID 0 layout. Each write is intercepted and synchronously replicated to the standby's equivalent EBS volume set.

References:
- [Amazon RDS Under the Hood: Multi-AZ](https://aws.amazon.com/blogs/database/amazon-rds-under-the-hood-multi-az/)
- [Implement high availability in Amazon RDS for SQL Server Web Edition using block-level replication](https://aws.amazon.com/blogs/database/implement-high-availability-in-amazon-rds-for-sql-server-web-edition-using-block-level-replication/)
- [Understanding Burst vs. Baseline Performance with Amazon RDS and GP2](https://aws.amazon.com/blogs/database/understanding-burst-vs-baseline-performance-with-amazon-rds-and-gp2/)
