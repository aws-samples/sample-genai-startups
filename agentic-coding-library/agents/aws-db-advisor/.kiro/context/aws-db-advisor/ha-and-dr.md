# High Availability & Disaster Recovery

Aurora Global Database, headless secondary clusters, RDS Multi-AZ (instance vs cluster), globally distributed identity, FDW patterns with Global Database, multi-region architecture.

**Glossary:** AZ = Availability Zone. CDC = Change Data Capture. FDW = Foreign Data Wrapper (PostgreSQL extension for querying remote databases). LSN = Log Sequence Number. RPO = Recovery Point Objective (maximum acceptable data loss). RTO = Recovery Time Objective (maximum acceptable downtime). WAL = Write-Ahead Log.

```
Architecture: Aurora Global Database topology

┌─────────────────────────┐         Storage-layer         ┌─────────────────────────┐
│   PRIMARY REGION        │        replication (<1s)       │   SECONDARY REGION      │
│                         │ ─────────────────────────────► │                         │
│  ┌───────┐  ┌───────┐  │                                │  ┌───────┐  ┌───────┐  │
│  │Writer │  │Reader │  │                                │  │Reader │  │Reader │  │
│  └───┬───┘  └───┬───┘  │                                │  └───┬───┘  └───┬───┘  │
│      │          │       │                                │      │          │       │
│  ════╪══════════╪═══    │                                │  ════╪══════════╪═══    │
│  Shared Storage (6 nodes)│                                │  Shared Storage (6 nodes)│
└─────────────────────────┘                                └─────────────────────────┘
```


## 27. Globally distributed identity with regionally constrained data

### Pattern

Authentication and identity are global (users can sign in from any region). Application data stays within the region dictated by compliance, data residency, or sovereignty requirements. The identity layer routes authenticated requests to the correct regional data store based on tenant or user metadata.

### AWS guidance

No single AWS reference architecture covers this end-to-end. The pattern is assembled from several sources:

**Hybrid architectures whitepaper** — the closest match. Covers using a global identity layer with local IdPs, keeping personal data in regional stores. Section 2.2 addresses the "Local IdP for authentication flow and storing user data" pattern directly.

**Data Residency with Hybrid Cloud Services Lens** — Well-Architected lens covering design principles for data residency across all six pillars. The announcement blog post gives a shorter overview.

**SaaS tenant isolation whitepaper** — covers identity-driven isolation patterns, including how tenant context flows from authentication into resource scoping. The identity and isolation section is the most relevant part.

**Global expansion prescriptive guidance** — three multi-account approaches (central landing zone with managed regions, regional landing zones, European Sovereign Cloud) for keeping data regionally constrained.

### Aurora Global Database consideration

Aurora Global Database supports regional reads with a single write region. Write forwarding allows secondary regions to forward writes to the primary. This is not data residency — all data replicates to all regions. For true data residency, use independent regional clusters with no cross-region replication.

References:
- [Hybrid Architectures to Address Personal Data Processing Requirements — Local IdP pattern](https://docs.aws.amazon.com/whitepapers/latest/hybrid-architectures-to-address-personal-data-processing-requirements/local-idp-for-authentication-flow-and-storing-user-data.html)
- [Data Residency with Hybrid Cloud Services Lens](https://docs.aws.amazon.com/wellarchitected/latest/data-residency-hybrid-cloud-services-lens/data-residency-with-hybrid-cloud-services-lens.html)
- [Announcing the Data Residency with Hybrid Cloud Services Lens](https://aws.amazon.com/blogs/architecture/announcing-the-well-architected-data-residency-with-hybrid-cloud-services-lens/)
- [SaaS Tenant Isolation Strategies whitepaper](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/saas-tenant-isolation-strategies.html)
- [Identity and isolation — SaaS Tenant Isolation Strategies](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/identity-and-isolation.html)
- [Empowering AWS Partners to expand their platforms globally](https://aws.amazon.com/blogs/publicsector/empowering-aws-partners-to-expand-their-platforms-globally/)
- [Strategizing for global expansion — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/privacy-reference-architecture/global-expansion.html)
- [Aurora Global Database write forwarding](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-write-forwarding.html)


## 28. Aurora Global Database architecture and operations

### How it works

Aurora Global Database replicates the entire cluster's data to secondary regions at the storage layer using storage block-based replication — not the database engine. One primary region handles all writes; secondary regions get read-only replicas with typical replication latency under one second.

This is distinct from PostgreSQL logical replication. Global Database replication operates on storage blocks; logical replication operates on WAL streams. The two mechanisms are independent and coexist — a Global Database writer can run zero-ETL integrations (for Redshift analytics) or logical replication slots (for pglogical or other subscribers) alongside the storage-layer cross-region replication.

### Configuration

- Up to five read-only secondary clusters in other AWS Regions. Regions can be added incrementally.
- Secondary regions can be "headless" — storage only, no compute. This saves cost until the region needs local reads. When the region goes live, attach a compute node to the existing storage.
- An existing Aurora DB cluster can be converted to a Global Database by adding a new Region to it. No snapshot/restore required.
- HA within each region follows standard Aurora patterns: two instances (multi-AZ).

### Failover

- Managed planned switchover (`SwitchoverGlobalCluster`): promotes a secondary cluster to primary while demoting the current primary to secondary. Synchronises all secondary clusters beforehand (RPO = 0). RTO under 1 minute.
- Unplanned failover: detach the secondary cluster and promote it to standalone. RPO of seconds (depends on replication lag at time of failure).
- Neither is automatic — the decision to promote must be deliberate. Can be automated with Lambda or EventBridge.

### Headless secondary clusters

A headless secondary cluster has no DB instances — storage only. Aurora's compute/storage decoupling means the secondary storage volume stays in sync with the primary via Global Database replication without any compute running. You pay only for storage and cross-region data transfer, not compute.

Supported for both Aurora MySQL and Aurora PostgreSQL.

**Setup:**

1. Add the secondary cluster normally (console, CLI, or API).
2. Wait for replication to start and the secondary cluster status to become `available`.
3. Delete the reader DB instance from the secondary cluster.

The cluster remains part of the Global Database. Its storage volume continues replicating from the primary.

For Aurora PostgreSQL: use the CLI or API to add the secondary region without creating a reader instance. The console requires creating and then deleting the instance. On PostgreSQL versions lower than 13.4, 12.8, or 11.13, deleting the reader instance can cause a vacuum issue on the primary writer — restart the primary writer after deletion if this occurs.

**Failover from a headless secondary:**

1. Add a DB instance to the headless cluster (`create-db-instance` with the secondary cluster identifier).
2. Wait for the instance to become available (several minutes depending on instance class and storage volume size).
3. Proceed with unplanned failover: detach the secondary and promote to standalone.

RTO is longer than a standard secondary because instance provisioning time is added. Expect 5–15 minutes total vs. under 1 minute with a running instance.

RPO is unaffected — the storage volume is kept in sync regardless of whether an instance is attached.

**When to use:**

- DR requirement exists but RTO of 5–15 minutes is acceptable.
- Cost sensitivity — eliminates secondary region compute charges entirely.
- Multiple secondary regions where only one needs fast failover (run one region with instances, others headless).

**When not to use:**

- RTO under 1 minute is required.
- Secondary region serves read traffic (no instances = no query endpoint).
- Write forwarding is needed from the secondary region.

References:
- [Creating a headless Aurora DB cluster in a secondary Region](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-attach.console.headless.html)
- [Achieve cost-effective multi-Region resiliency with Amazon Aurora Global Database headless clusters](https://aws.amazon.com/blogs/database/achieve-cost-effective-multi-region-resiliency-with-amazon-aurora-global-database-headless-clusters/)

### Write forwarding (cross-region)

Write forwarding on Global Database allows applications connected to a secondary region's reader to issue writes. Aurora forwards those writes to the primary region's writer, commits them there, and returns the result. The application doesn't need to know it's connected to a secondary.

Version support: Aurora PostgreSQL 16+ (all minor versions), 15.4+, 14.9+. Enabling or disabling write forwarding doesn't cause downtime or a reboot.

Consistency modes — controlled per session via `apg_write_forward.consistency_mode`:

| Mode | Behaviour | Use case |
|---|---|---|
| `SESSION` (default) | After a write, subsequent reads in the same session wait for that write to replicate back. Other sessions unaffected. | User updates profile and immediately sees the change |
| `EVENTUAL` | Reads proceed without waiting. May return stale data. | Background writes where stale reads are acceptable |
| `GLOBAL` | Every read waits for full consistency with the primary, even reads that didn't follow a write. | Cross-session consistency — adds latency to all reads |
| `OFF` | Write forwarding disabled for the session. Writes fail. | Enforcing read-only sessions |

Latency: each forwarded write adds the cross-region round-trip. London to Dublin is ~10-15ms, so a forwarded commit adds roughly 20-30ms. Acceptable for infrequent writes (profile updates, preference changes), not for sustained high-throughput ingestion.

Unsupported SQL: DDL statements, cursors, user-defined functions, and `SAVEPOINT` cannot be forwarded. Standard DML (INSERT, UPDATE, DELETE, SELECT) works.

Connection limits: `apg_write_forward.max_forwarding_connections_percent` (default 25%) caps the percentage of `max_connections` on the writer used for forwarded sessions.

### Networking

Aurora manages cross-region networking internally for both storage-layer replication and write forwarding. No customer-managed VPC peering or Transit Gateway required for these features.

Cross-region networking is only needed for application-level cross-region connections: FDWs from one region's cluster to another region's cluster, or CDC connections from a regional cluster to a remote analytics system.

### Monitoring

CloudWatch metrics (cluster-level, published in the secondary region):

| Metric | Description |
|---|---|
| `AuroraGlobalDBReplicationLag` | Replication lag in milliseconds between primary and secondary clusters. Target: under 1,000ms. |
| `AuroraGlobalDBRPOLag` | Time difference between the most recent committed user transaction on the primary and the most recent stored on the secondary. Measures potential data loss in failover. |
| `AuroraGlobalDBProgressLag` | How far behind the secondary cluster is for both user and system transactions. |
| `AuroraGlobalDBDataTransferBytes` | Bytes of redo log data transferred from primary to secondary. |
| `AuroraGlobalDBReplicatedWriteIO` | Write I/O operations replicated from primary to secondary. Used in billing calculations. |

PostgreSQL functions (run from any instance in the global database):

```sql
-- Cross-region storage lag per cluster
SELECT aws_region, highest_lsn_written,
       durability_lag_in_msec, rpo_lag_in_msec,
       last_lag_calculation_time
FROM aurora_global_db_status();

-- Per-instance replication status
SELECT server_id, aws_region, durable_lsn,
       highest_lsn_received, visibility_lag_in_msec
FROM aurora_global_db_instance_status();
```

Recommended alarms: `AuroraGlobalDBReplicationLag` > 2,000ms sustained for 5 minutes; `AuroraGlobalDBRPOLag` > 5,000ms.

### RPO enforcement with `rds.global_db_rpo`

Aurora PostgreSQL Global Database provides the `rds.global_db_rpo` cluster parameter to enforce a maximum RPO by throttling commits on the primary writer when secondary clusters fall behind.

**How it works:**

1. Set the parameter on the **primary** cluster's DB cluster parameter group (value in seconds).
2. Aurora continuously monitors the RPO lag time to all secondary clusters.
3. If at least one secondary cluster has lag below the threshold — commits proceed normally.
4. If all secondary clusters have lag exceeding the threshold — Aurora blocks commits on the primary writer until at least one secondary catches up.

Blocked sessions emit PostgreSQL "wait" events and are logged to the PostgreSQL log file. The parameter is dynamic — changes take effect without a restart after a short delay.

| Property | Value |
|----------|-------|
| Engine | Aurora PostgreSQL only |
| Valid range | 20 – 2,147,483,647 seconds |
| Default | -1 (disabled) |
| Apply type | Dynamic (no restart required) |
| Where to set | Primary cluster's DB cluster parameter group |

**Setting the value:**

```bash
aws rds modify-db-cluster-parameter-group \
    --db-cluster-parameter-group-name my_custom_global_parameter_group \
    --parameters "ParameterName=rds.global_db_rpo,ParameterValue=600,ApplyMethod=immediate"
```

**Viewing the current value** (connect to any cluster instance):

```sql
SHOW rds.global_db_rpo;
-- Returns -1 if disabled, otherwise the threshold in seconds
```

**Disabling:**

```bash
aws rds reset-db-cluster-parameter-group \
    --db-cluster-parameter-group-name my_custom_global_parameter_group \
    --parameters "ParameterName=rds.global_db_rpo,ApplyMethod=immediate"
```

**Two-region caveat:** In a global database with only two regions, keep the default (-1, disabled) on the secondary region's parameter group. If the primary region is lost and the secondary is promoted, it becomes the writer. If `rds.global_db_rpo` is set but no valid secondary exists (the old primary is rebuilding), Aurora blocks all commits waiting for a secondary that will not catch up. Wait until the old primary is rebuilt as a healthy secondary before enabling this parameter on the new primary.

**Sizing guidance:** Set the value to match your contractual RPO. For a 5-minute RPO target, use 300. For 10 minutes, use 600. The trade-off is write availability: a tighter value means commits block more readily during replication lag spikes (network blips, high write bursts, storage node recovery).

References:
- [Managing RPOs for Aurora PostgreSQL–based global databases](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html#aurora-global-database-manage-recovery)
- [Modifying parameters for an Aurora global database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-modifying.parameters.html)

### Customer reference

Standard Chartered Bank migrated core banking (Atlas) from DB2 to Aurora PostgreSQL and uses Aurora Global Database for cross-region DR. After migrating 7 markets they achieved 4,000 TPS (10x previous throughput). As of November 2024, migrated across 26 global markets. Their cross-region DR uses a pilot-light model — database continuously replicated via Global Database, rest of infrastructure down until needed. Adds less than 10% additional infrastructure cost with cross-region RPO of seconds.

### Secondary storage health and failover readiness

The secondary cluster's storage health determines whether failover completes in seconds or hours. If the secondary volume cannot achieve write quorum at promotion time, Aurora falls back to restoring from a snapshot — which can take hours depending on volume size.

**Causes of unhealthy secondary storage:**
- Hardware failures on storage nodes within a protection group (Aurora distributes data across six nodes in three AZs per 10 GB protection group)
- Network disruptions between regions leaving gaps in LSN sequences
- High write throughput overwhelming the replication backlog
- Gossip protocol failures between storage nodes preventing resynchronisation

**Monitoring secondary health:**

```sql
SELECT * FROM aurora_show_volume_status();
-- Track Nodes count; a decrease indicates storage node failures

SELECT * FROM aurora_global_db_status();
-- durability_lag_in_msec increasing = storage falling behind

SELECT * FROM aurora_global_db_instance_status();
-- Gap between highest_lsn_received and durable_lsn = storage backlog
```

CloudWatch alarms to set:
- `AuroraGlobalDBRPOLag` > your RPO target (e.g. 5000 ms) sustained for 5 minutes
- `AuroraGlobalDBDataTransferBytes` drops to 0 for > 1 minute

EventBridge rules: subscribe to RDS Events 0512 ("Volume replacement started"), 0513 ("Volume replacement completed"), 0240, 0241, and 0069.

**Prevention:**
1. Upgrade to Aurora PostgreSQL 16.6+ (or 15.10/14.15/13.18/12.22+) for cross-region storage resiliency improvements
2. Perform planned switchovers at least quarterly to validate write quorum
3. Monitor `aurora_show_volume_status()` on a schedule
4. Set `rds.global_db_rpo` to throttle primary commits if secondary falls behind

### Switchover vs failover for DR testing

| Characteristic | Switchover | Failover |
|---|---|---|
| Purpose | Planned DR testing, regional rotation | Unplanned outage recovery |
| Data loss | Zero (synchronises before switching) | Seconds (equals replication lag) |
| Old primary | Automatically demoted to secondary; no rebuild | Volume replaced; rebuilt from snapshot |
| Topology | Preserved | Preserved (managed) or must rebuild (manual) |
| Duration | Under 30 seconds (supported versions) | Minutes for writer; hours for full rebuild |
| API | `SwitchoverGlobalCluster` | `FailoverGlobalCluster --allow-data-loss` |

**Always use switchover for DR testing.** Using failover for testing introduces unnecessary risks: data loss, lengthy volume rebuilds, and a period with no secondary read capacity. Switchover avoids all of these because it synchronises before acting.

**Fast switchover requirements:** Aurora PostgreSQL 16.8/15.12/14.17/13.20+ or Aurora MySQL 3.09+.

**Recommended cadence:** Quarterly minimum. Monthly for tier-0 workloads. Because switchover is now under 30 seconds with zero data loss, the barrier to frequent testing is low.

### Configuration audit checklist

Common gaps that cause failover issues:

1. Application using cluster endpoint instead of global writer endpoint — use `<global-cluster-name>.global-<id>.global.rds.amazonaws.com`
2. Secondary instance class undersized relative to primary writer — nothing is inherited during promotion
3. No CloudWatch alarms on replication lag metrics
4. Parameter groups diverged between primary and secondary (check `rds.global_db_rpo`, `max_connections`, timezone)
5. Backup retention at default (1 day) on secondary — set to at least 14 days
6. Maintenance windows not staggered — primary writer restart during maintenance also restarts secondary readers
7. Engine versions drifted or patch levels mismatched — primary and secondary must share same version for switchover
8. DNS TTL not reduced below 30 seconds
9. No VPC connectivity pre-established between application region and secondary region

### Layered DR strategy

| Layer | Protects against | Mechanism | RPO | RTO |
|-------|-----------------|-----------|-----|-----|
| Primary DR | Regional outage | Global Database with running instances | Seconds | Under 1 minute |
| Data corruption | Application bugs, accidental deletes | PITR (35-day retention) | ~5 minutes | 15-60 min |
| Cross-region backup | Regional loss of backup infrastructure | AWS Backup cross-region snapshot copies | Up to 24 hours | 30-60 min |
| Immutable audit trail | Total loss of both regions | CDC to S3 (logical replication) | Seconds to minutes | Hours |
| Account-level protection | Ransomware, account compromise | AWS Backup cross-account + vault lock | Up to 24 hours | 30-60 min |
| Operational safety | Maintenance errors | Blue/Green Deployments | 0 | Under 1 minute |

Key points:
- PITR creates a standalone cluster; you must manually re-add it to a global database
- AWS Backup cross-region copies are periodic snapshots — you cannot do PITR from a cross-region copy
- Vault Lock provides immutable backups that cannot be deleted, even by root
- Blue/Green Deployments with Global Database preserve DR capabilities during maintenance operations

References:
- [Using Amazon Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [Aurora global databases — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/aurora-replication-options/aurora-global-database.html)
- [Comparing Aurora replication solutions — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/aurora-replication-options/compare-solutions.html)
- [Getting started with Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-getting-started.html)
- [Adding an AWS Region to an Aurora global database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-attaching.html)
- [Creating a headless Aurora DB cluster in a secondary Region](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-attach.console.headless.html)
- [SwitchoverGlobalCluster API](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_SwitchoverGlobalCluster.html)
- [Automating DR for Aurora Global Database — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/automate-dr-solution-relational-database/aurora-state-machines.html)
- [Using write forwarding in an Aurora PostgreSQL global database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-write-forwarding-apg.html)
- [Monitoring Aurora PostgreSQL-based global databases](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-monitoring.html)
- [aurora_global_db_status function](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora_global_db_status.html)
- [Cross-Region resiliency for Global Database secondary clusters](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-secondary-availability.html)
- [Aurora Global Database switchover under 30 seconds (May 2025)](https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-aurora-cross-region-global-database-switchover-time-under-30-seconds/)
- [Aurora Global Database disaster recovery](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html)
- [Aurora PostgreSQL volume status](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Managing.VolumeStatus.html)
- [RDS event messages](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_Events.Messages.html)
- [Well-Architected Framework — REL13-BP03: Test disaster recovery](https://docs.aws.amazon.com/wellarchitected/2023-10-03/framework/rel_planning_for_recovery_dr_tested.html)
- [Aurora point-in-time recovery](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-pitr.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [Aurora Global Database Blue/Green Deployments](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-bluegreen.html)
- [Aurora Storage Engine (blog)](https://aws.amazon.com/blogs/database/introducing-the-aurora-storage-engine/)
- [Amazon Aurora Global Database product page](https://aws.amazon.com/rds/aurora/global-database/)
- [Amazon Aurora for Core Banking Systems — AWS Industries Blog](https://aws.amazon.com/blogs/industries/amazon-aurora-for-core-banking-systems/)
- [Standard Chartered Bank: Migrating core banking to AWS — AWS re:Invent 2021 (FSI303)](https://youtu.be/xRDGFiGMfXA)
- [Use Amazon Aurora Global Database to build resilient multi-Region applications](https://aws.amazon.com/blogs/database/use-amazon-aurora-global-database-to-build-resilient-multi-region-applications)
- [Scale applications using multi-Region Amazon EKS and Amazon Aurora Global Database](https://aws.amazon.com/blogs/database/part-2-scale-applications-using-multi-region-amazon-eks-and-amazon-aurora-global-database/)


## 31. FDW patterns with Aurora Global Database

### Same-region FDWs via Global Database local readers

When Aurora Global Database provides a local reader in every region, regional clusters can use `postgres_fdw` to connect to the local Global Database reader — not cross-region. This eliminates cross-region latency for FDW queries.

FDW latency becomes same-region (~600us same-AZ, ~1.6ms cross-AZ) instead of cross-region (~10-15ms). The application connecting to the regional cluster can JOIN local tables with foreign tables from the Global Database reader transparently.

### FDW limitations with foreign tables

- No FK constraints between foreign tables and local tables. PostgreSQL does not support `FOREIGN KEY` referencing a foreign table. Referential integrity must be application-enforced.
- Query pushdown works: a SELECT with a WHERE clause on a foreign table pushes the filter to the remote side. A SELECT without a WHERE clause ships the entire table.
- Triggers on foreign tables fire on the home cluster (where the foreign table is defined), not on the remote cluster.

### Materialised view fallback

If the Global Database reader in a region goes down, FDW queries fail. Materialised views with auto-refresh (via pg_cron) provide a fallback — the MV serves stale data during an outage, and a failed refresh doesn't empty or corrupt the existing view.

```sql
CREATE MATERIALIZED VIEW mv_individuals AS
SELECT * FROM foreign_individual_table;

-- Refresh every 5 minutes via pg_cron
SELECT cron.schedule('refresh-individuals', '*/5 * * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY mv_individuals$$);
```

`REFRESH MATERIALIZED VIEW CONCURRENTLY` requires a unique index on the materialised view. It allows reads during refresh.

### Reverse-direction FDWs for aggregated views

For aggregated views across regions (e.g. "show all data for this customer across all regions"), FDWs can be defined on the Global Database writer pointing to each regional cluster. The writer is the only node that can execute DDL (`CREATE SERVER`, `CREATE FOREIGN TABLE`), so reverse-direction FDWs must live there.

These are cross-region connections (writer in primary region → regional clusters in other regions), unlike the forward-direction FDWs which are same-region.

As regions multiply, application-level fan-out (query each regional cluster in parallel, merge results in the application) scales better than adding cross-region FDWs to the writer.

### FDW lifecycle management

FDW definitions are DDL. Each regional cluster needs its own migration pipeline because FDW definitions differ per region (different foreign server endpoints, different user mappings). A source table schema change (e.g. adding a column) requires coordinated updates: source table migration first, then each regional cluster's foreign table definition updated.

Liquibase with `runOnChange="true"` handles this — modifications to foreign table definitions are detected and re-applied automatically.

References:
- [Using the postgres_fdw extension — Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/postgresql-commondbatasks-fdw.html)
- [Aurora PostgreSQL database integration — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/aurora-postgresql-integration/aurora-db-integration.html)
- [PostgreSQL CREATE FOREIGN TABLE](https://www.postgresql.org/docs/current/sql-createforeigntable.html)
- [PostgreSQL materialised views](https://www.postgresql.org/docs/current/rules-materializedviews.html)


## 32. Multi-region architecture: global identity with regional data

### Pattern

Split the database layer into two tiers:

1. Aurora Global Database for globally shared data (identity, auth, preferences). Writer in the primary region, read-only replicas in every region. Write forwarding for non-primary region writes.

2. Standalone regional Aurora PostgreSQL clusters for regionally constrained data (operational data that differs per market). Independent clusters with no cross-region replication.

3. FDWs from each regional cluster to the local Global Database reader (same-region) to JOIN global and regional data without cross-region latency.

### When this pattern applies

- Global identity/auth needed everywhere, but operational data must stay regional
- Regional schemas differ between markets (different regulatory requirements, different data fields)
- Write volume on regional data is high (write forwarding not suitable for sustained throughput)
- Write volume on global data is low (write forwarding acceptable for infrequent updates)

### Onboarding consistency

Cross-layer consistency during onboarding is an application orchestration problem, not a replication problem. The flow is sequential: create global records first (identity, auth), then create regional records (operational data). The application carries IDs forward in the same request flow. Cross-region latency adds ~30-50ms total — invisible to the user.

### Data residency

Under GDPR, data residency within the EU is not mandatory. The EU-US Data Privacy Framework (DPF), adopted by the European Commission on 10 July 2023, provides an adequacy decision for transfers of personal data from the EU to certified US organisations. AWS participates in the DPF.

Sector-specific regulations may impose additional constraints on data location. The architecture works regardless of whether the driver is legal or operational — regional clusters provide lower latency, independent scaling, blast radius containment, and simpler compliance posture.

Aurora Global Database is not data residency — it replicates everything everywhere. For true data residency, use independent regional clusters with no cross-region replication.

### Migration strategy

Phase 1: Convert existing Aurora cluster to Global Database by adding a new Region. Secondary regions can start headless (storage only, no compute) to save cost.

Phase 2: Create standalone regional cluster in the first expansion region. Set up FDWs to local Global Database reader. Validate end-to-end.

Phase 3: Run for 3-6 months. Measure FDW query latency, Global Database replication lag, cross-region CDC throughput.

Phase 4: Repeat for additional regions.

References:
- [AWS — EU-US Data Privacy Framework](https://aws.amazon.com/compliance/eu-us-data-privacy-framework/)
- [European Commission — adequacy decision for the EU-US Data Privacy Framework (July 2023)](https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/eu-us-data-transfers_en)


## 34. RDS Multi-AZ: instance deployment vs cluster deployment

### Multi-AZ DB instance deployment (one standby)

- 1 primary + 1 passive standby in a different AZ
- Synchronous block-level replication (Amazon failover technology; SQL Server uses DBM/AGs)
- Standby cannot serve read traffic
- Failover: 60-120 seconds, independent of write throughput. Large transactions or lengthy recovery can extend this.
- Backups taken from standby (no I/O suspension on primary)
- Uses Dedicated Log Volumes for lower jitter
- Supported engines: PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, Db2
- Can convert Single-AZ to Multi-AZ with no downtime
- Supports stop/start, storage autoscaling, snapshot copy

References:
- [Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html)
- [Multi-AZ DB instance failover](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.Failover.html)

### Multi-AZ DB cluster deployment (two readable standbys)

- 1 writer + 2 readers across 3 AZs
- Semisynchronous engine-native replication (requires ack from at least one reader before commit)
- Readers serve read traffic via a separate reader endpoint
- Failover: typically under 35 seconds, but depends on replica lag
- Up to 2x faster transaction commit latency vs single-standby mode
- Uses local NVMe storage for transaction logs (reduces jitter)
- Supported engines: PostgreSQL and MySQL only
- Minor version upgrades: under 35 seconds alone, under 1 second with RDS Proxy or the AWS JDBC Wrapper
- Supports RDS Proxy (connection multiplexing, faster upgrades)
- Has DB cluster parameter groups (applied to all instances in the cluster)
- Flow control available to throttle writes and contain replica lag
- Requires NVMe-backed instance classes: db.m5d, db.m6gd, db.m6id, db.m6idn, db.r5d, db.r6gd, db.r6id, db.r6idn, db.x2iedn, db.c6gd

References:
- [Multi-AZ DB cluster deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html)
- [Multi-AZ DB cluster failover](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts-failover.html)
- [RDS Multi-AZ comparison](https://aws.amazon.com/rds/features/multi-az/)

### Multi-AZ DB cluster limitations

- No IPv6 / dual-stack connections
- No cross-region automated backups
- No Kerberos authentication
- Cannot modify the port after creation (workaround: restore to point-in-time with a different port)
- No option groups
- No PITR for deleted clusters
- No storage autoscaling (manual scaling only)
- Cannot stop/start the cluster
- Cannot copy a cluster snapshot
- Cannot encrypt an unencrypted cluster after creation
- GP3 storage bandwidth capped at 500 Mbit/sec due to 8K block size. This limit does not apply to io2 storage.
- PostgreSQL: extensions aws_s3 and pg_transport not supported; custom DNS servers for outbound network access not supported
- MySQL: only five system stored procedures supported (rds_rotate_general_log, rds_rotate_slow_log, rds_show_configuration, rds_set_external_master_with_auto_position, rds_set_configuration)

References:
- [Limitations of Multi-AZ DB clusters](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.Limitations.html)

### Comparison

| Dimension | Multi-AZ instance (1 standby) | Multi-AZ cluster (2 readable standbys) |
|---|---|---|
| Engines | PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, Db2 | PostgreSQL, MySQL |
| Read capacity from standbys | None | Yes, via reader endpoint |
| Replication | Synchronous, block-level | Semisynchronous, engine-native |
| Failover time | 60-120 seconds | Typically under 35 seconds |
| Failover dependency | Independent of write throughput | Depends on replica lag |
| Commit latency | Baseline | Up to 2x faster |
| Transaction log storage | Dedicated Log Volumes | Local NVMe |
| Minor version upgrade downtime | During maintenance window | Under 35s (under 1s with Proxy) |
| Stop/start support | Yes | No |
| Storage autoscaling | Yes | No |
| GP3 storage bandwidth | No 500 Mbit/sec cap | Capped at 500 Mbit/sec (8K block size); io2 not capped |

### When to use which

Multi-AZ instance:
- Need MariaDB, SQL Server, Oracle, or Db2
- Need stop/start, storage autoscaling, or snapshot copy
- 60-120 second failover is acceptable
- No read scaling from standbys required
- Need uncapped GP3 storage bandwidth

Multi-AZ cluster:
- PostgreSQL or MySQL
- Faster failover required (under 35 seconds)
- Read capacity from standbys needed
- Lower write commit latency needed
- Can accept NVMe instance class requirement and the limitations above
- GP3 500 Mbit/sec storage bandwidth cap is acceptable, or using io2
