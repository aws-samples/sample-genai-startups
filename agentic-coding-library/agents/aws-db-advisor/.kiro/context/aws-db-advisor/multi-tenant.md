# Multi-Tenant Aurora PostgreSQL

Bin-packing, schema isolation, connection pool fragmentation, single-tenant restore, pglogical consolidation.


## 19. Multi-tenant Aurora PostgreSQL

### Bin-packing effect

Consolidating multiple Serverless v2 clusters onto a single cluster creates a bin-packing effect where individual tenant spikes average out. With 50+ tenants, spikes are statistically unlikely to align, producing a smoother aggregate load.

Consequence: Sustained average utilisation increases, potentially crossing the 25% threshold where provisioned instances become cheaper than Serverless v2. Model this before consolidating by summing `ServerlessDatabaseCapacity` metrics across all clusters at each timestamp over 30 days.

Trade-off: Improved cost efficiency at the expense of increased blast radius.

### Schema isolation strategy

Use the bridge model with separate databases per tenant. Each tenant gets their own PostgreSQL database within the consolidated Aurora cluster.

Separate databases:
- Moderate data isolation
- Easier tenant extraction (can migrate back to dedicated cluster)
- Per-database connection limits
- Requires separate connection pool per database
- No `SET search_path` required — database boundary provides isolation
- Explicit control over pool size per database and better monitoring of per-tenant connection usage

Separate schemas (alternative):
- Faster tenant onboarding
- Simpler connection pooling (single database)
- Weaker isolation, shared autovacuum
- Causes connection pool fragmentation with PgBouncer (see below)
- RDS Proxy not viable due to session pinning from `SET search_path`

Shared tables with RLS (not recommended for SaaS):
- Highest risk of data leakage
- Complex vacuum and index management
- Difficult to extract individual tenants

### Connection pool fragmentation (schema-per-tenant)

PgBouncer creates separate connection pools based on the entire connection string, including the `options` parameter. Setting `search_path` via options creates distinct pools per tenant:

```
1 database with 200 different connection strings
= 200 separate pools
= 5000 connections / 200 pools
= 25 connections per tenant (fragmented)
```

Any `SET` command (including `SET search_path`) pins the PostgreSQL session to a specific database connection in RDS Proxy. PostgreSQL has no session pinning filters (unlike MySQL/MariaDB which track 20+ variables). Pinned connections cannot be reused until session ends, eliminating the primary benefit of RDS Proxy (connection multiplexing).

Conclusion: RDS Proxy is not viable for schema-per-tenant architecture.

### Heimdall Proxy multi-tenant support

Heimdall routes to different databases or clusters, not different schemas within the same database. Cannot dynamically set `search_path` for schema routing. Requires database-per-tenant migration first.

| Architecture | Heimdall Support |
|--------------|------------------|
| Database-per-tenant | Yes |
| Schema-per-tenant | No |
| Cluster-per-tenant | Yes |

### Single-tenant restore complexity

Aurora snapshots and PITR restore the entire cluster. Restoring a single tenant's database requires a workaround:

1. Restore entire cluster to point-in-time (creates temporary cluster)
2. Extract single tenant database using `pg_dump -Fc`
3. Drop and recreate corrupted database on production
4. Restore using `pg_restore -j 4`
5. Delete temporary cluster

Downtime per tenant: 15-30 minutes depending on database size.

Alternative: Automated tenant-level backups using pg_dump to S3 on a daily schedule. Faster restore (no temporary cluster provisioning), lower cost, but backup frequency limited by schedule vs continuous PITR.

### Consolidation migration using pglogical

The `pglogical` extension provides near-zero downtime migration for consolidating multiple Aurora PostgreSQL clusters into one.

Why pglogical over native logical replication:
- Supports replication between different PostgreSQL versions
- Two-way replication capability
- Better handling of sequences and DDL changes

Process:
1. Create target cluster with separate databases per tenant
2. Enable `wal_level = logical`, `max_replication_slots`, `max_wal_senders` on source (requires reboot)
3. Install pglogical extension on source and target
4. Create publisher node on source, add tables to replication set
5. Create subscriber node on target with subscription to source
6. Monitor initial sync: `SELECT * FROM pglogical.show_subscription_status();`
7. Monitor lag: `SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) FROM pg_replication_slots WHERE slot_type = 'logical';`
8. Cutover: Stop writes, verify lag = 0, switch connection strings, drop subscription

Downtime per tenant: 1-2 minutes.

Alternative: AWS DMS homogeneous migration if pglogical is not suitable (version incompatibilities). DMS is best suited for one-time migration tasks rather than long-running continuous replication.

References:
- [PostgreSQL bridge model](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/bridge.html)
- [Multi-tenant SaaS partitioning decision matrix](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/matrix.html)
- [Restoring a DB cluster to a specified time](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-pitr.html)
- [Using pglogical to synchronize data across instances](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.pglogical.html)
- [Setting up the pglogical extension](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.pglogical.basic-setup.html)
- [Overview of PostgreSQL logical replication with Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.html)
- [PostgreSQL pglogical extension — Database Migration Guide](https://docs.aws.amazon.com/dms/latest/sbs/chap-manageddatabases.postgresql-rds-postgresql-full-load-pglogical.html)
- [AWS RDS Proxy Session Pinning](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html)
- [Heimdall Data Multi-Tenant Routing](https://aws.amazon.com/blogs/apn/multi-tenant-customer-routing-for-amazon-rds-and-amazon-redshift-with-heimdall-data/)
