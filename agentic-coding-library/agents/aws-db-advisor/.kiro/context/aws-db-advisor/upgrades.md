# RDS and Aurora upgrade best practices



## Overview

Major and minor version upgrades on Amazon RDS and Aurora are routine operations, but without proper preparation they can result in unexpected failures, extended downtime, or data access issues. This document captures field-tested best practices for planning, testing, executing, and recovering from upgrade failures.



## Before the upgrade

### 1. Test the upgrade path on a snapshot restore

Always test the upgrade path on a snapshot restore before upgrading production.

1. Identify a recent automated snapshot of the production cluster or instance.
2. Restore it to an isolated cluster (different identifier, same region, same instance class).
3. Modify the engine version to the target version.
4. Monitor the upgrade process through the Events console and engine error logs.
   - If the upgraded instance starts cleanly: production data is compatible with the target version. Proceed with the production upgrade plan.
   - If it fails (assertion errors, crash loops, startup failures): do not attempt the same upgrade on production. Engage AWS Support (see "When upgrades fail" below).

This single step catches the majority of upgrade-path issues before they affect production.

References:
- [Restoring from a DB cluster snapshot (Aurora)](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-restore-snapshot.html)
- [Restoring from a DB snapshot (RDS)](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RestoreFromSnapshot.html)

### 2. Understand your version support timeline

Both RDS and Aurora publish end-of-standard-support dates for each engine version. When a version reaches end of support, AWS will upgrade it automatically — even with Auto Minor Version Upgrade disabled. The automatic upgrade targets the "default minor version" at that time (typically the latest LTS patch).

Proactively upgrading on your schedule, with testing, is always preferable to a forced automatic upgrade.

References:
- [Aurora MySQL Long-Term Support releases](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraMySQL.Updates.Versions.html#AuroraMySQL.Updates.LTS)
- [Aurora MySQL release calendars](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraMySQLReleaseNotes/AuroraMySQL.release-calendars.html)
- [Aurora PostgreSQL Long-Term Support releases](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Updates.LTS.html)
- [Aurora PostgreSQL release calendars](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.release-calendars.html)
- [Upgrading Amazon Aurora DB clusters](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.VersionPolicy.Upgrading.html)
- [RDS for MySQL version support policy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/MySQL.Concepts.VersionMgmt.html)
- [RDS for PostgreSQL version support policy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.DBVersions.html)

### 3. Review the pre-upgrade checks

Aurora and RDS provide automated pre-upgrade checks that flag incompatibilities before the upgrade begins. Run them manually before scheduling the upgrade window:

- **Aurora MySQL:** run the `mysqlcheck` utility and review the upgrade prechecks log group in CloudWatch (`/aws/rds/cluster/<cluster-id>/upgrade-prechecks`).
- **RDS for MySQL:** the pre-upgrade validation runs automatically and surfaces issues in the Events console.
- **Aurora PostgreSQL:** review the `pg_upgrade_internal.log` published to CloudWatch Logs after the upgrade attempt. The log is available even on failed upgrades and contains the specific error that caused the failure. Common issues include unsupported data types, extensions requiring updates, and objects owned by deleted roles.
- **RDS for PostgreSQL:** the same `pg_upgrade` process runs internally. Check the Events console and the `pg_upgrade_internal.log` file (available via the `rds_pg_upgrade_logs` log group or by downloading from the console).

References:
- [Aurora MySQL upgrade prechecks](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraMySQL.Updates.MajorVersionUpgrade.html#AuroraMySQL.Upgrading.Prechecks)
- [Upgrading the PostgreSQL DB engine for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_UpgradeDBInstance.PostgreSQL.html)
- [Upgrading a PostgreSQL DB instance (RDS)](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.PostgreSQL.html)
- [How to upgrade PostgreSQL major versions using pg_upgrade](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.PostgreSQL.html#USER_UpgradeDBInstance.PostgreSQL.MajorVersion)

### 4. PostgreSQL-specific preparation

Before attempting a major version upgrade on Aurora PostgreSQL or RDS for PostgreSQL:

- **Update extensions.** Drop or update extensions that are not supported on the target version. Check compatibility with:
  ```sql
  SELECT name, default_version, installed_version
  FROM pg_available_extensions
  WHERE installed_version IS NOT NULL;
  ```

- **Remove references to deleted roles.** Objects owned by roles that no longer exist will cause `pg_upgrade` to fail. Identify them with:
  ```sql
  SELECT d.datname, c.relname, c.relkind, c.relowner
  FROM pg_class c
  JOIN pg_database d ON true
  WHERE c.relowner NOT IN (SELECT oid FROM pg_roles);
  ```

- **Drop the `unknown` data type.** Columns using the `unknown` type block upgrades from PostgreSQL 9.x/10.x to later versions.

- **Handle `reg*` data type columns.** Columns of type `regclass`, `regtype`, `regproc`, etc. in user tables can cause upgrade failures if they reference objects that may have different OIDs post-upgrade.

- **Resolve prepared transactions.** Any transaction in the `prepared` state (`PREPARE TRANSACTION`) will block `pg_upgrade`. Commit or roll them back before starting.

- **Drop logical replication slots.** Existing logical replication slots on the source must be dropped before an in-place major version upgrade (they are not preserved by `pg_upgrade`).

References:
- [Upgrading the PostgreSQL DB engine for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_UpgradeDBInstance.PostgreSQL.html)
- [How to perform a major version upgrade for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_UpgradeDBInstance.PostgreSQL.html#USER_UpgradeDBInstance.PostgreSQL.MajorVersion)
- [PostgreSQL extensions supported by Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Extensions.html)

### 5. Maintain binary log or WAL retention

For MySQL/Aurora MySQL, retain at least 72 hours of binary logs:

```sql
CALL mysql.rds_set_configuration('binlog retention hours', 72);
```

For PostgreSQL/Aurora PostgreSQL, if you plan to use logical replication as a fallback migration path, ensure the source is configured for it:

```sql
-- Set via the DB cluster/instance parameter group:
-- rds.logical_replication = 1
-- wal_sender_timeout = 0  (or a high value, to avoid timeout during large initial syncs)
```

Changing `rds.logical_replication` requires a reboot. Do this in advance — not during an emergency migration.

This provides a fallback window if you need to perform a logical migration instead of an in-place upgrade.

References:
- [mysql.rds_set_configuration](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/mysql-stored-proc-configuring.html#mysql_rds_set_configuration)
- [Logical replication for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.html)
- [Logical replication for RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html#PostgreSQL.Concepts.General.FeatureSupport.LogicalReplication)



## Executing the upgrade

### Blue/Green Deployment (recommended for production)

Blue/Green Deployment is the safest managed upgrade path for production workloads:

1. Aurora/RDS creates a "Green" staging environment from a snapshot of your production ("Blue") cluster.
2. The Green environment is upgraded to the target version.
3. Logical replication keeps Green in sync with ongoing Blue changes.
4. When ready, a managed switchover completes in approximately 30 seconds of downtime (or less with RDS Proxy).
5. Rollback is available if issues are detected post-switchover.

If your cluster is already fronted by RDS Proxy, the proxy detects the switchover and redirects connections automatically — eliminating DNS propagation delay entirely.

**Requirement:** the cluster must already be a target of the proxy *before* you create the Blue/Green deployment.

**Note on PostgreSQL:** Blue/Green Deployments support Aurora PostgreSQL and RDS for PostgreSQL. For PostgreSQL major version upgrades, the Green environment uses `pg_upgrade` internally — the same mechanism as an in-place upgrade, but with the safety of the Blue environment remaining untouched until switchover.

References:
- [Using Amazon Aurora Blue/Green Deployments for database updates](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments.html)
- [Using Amazon RDS Blue/Green Deployments (RDS for PostgreSQL)](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments.html)
- [Switching a Blue/Green deployment](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-switching.html)
- [Using RDS Proxy with Blue/Green Deployments](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy-blue-green.html)

### In-place upgrade

For non-production environments or where Blue/Green is not available, in-place modification is acceptable — provided you have tested the upgrade path on a snapshot first.

1. Schedule the upgrade during a low-traffic maintenance window.
2. For RDS Multi-AZ instances (not Aurora): the upgrade applies to the standby first, then fails over, reducing downtime. For Aurora clusters, all instances are upgraded simultaneously regardless of how many readers exist — Multi-AZ does not help reduce upgrade downtime.
3. Monitor the Events console and engine error logs throughout.



## When upgrades fail

### Symptoms

Upgrade failures can manifest as:

- The instance entering a crash-loop or remaining in "incompatible-parameters" / "storage-full" / "failed" state.
- Assertion errors in the engine error log (e.g. InnoDB undo tablespace assertions for MySQL).
- For PostgreSQL: `pg_restore` errors during constraint or index restoration, connection termination (`FATAL: terminating connection due to administrator command`), or `pg_upgrade` reporting the cluster cannot be upgraded.
- The upgrade appearing to complete but the instance failing to start on the new version.
- Mysterious or unexplained errors with no clear root cause in the event log.

### Retrying a failed upgrade

In some cases, an upgrade that initially fails will succeed on a subsequent attempt. This can occur when:

- Transient infrastructure issues (storage subsystem hiccups, resource contention) caused the initial failure.
- Background maintenance or recovery processes completed between attempts.
- The failure was timing-dependent rather than caused by data incompatibility.

If an upgrade fails and the error is not clearly tied to a data incompatibility or precondition violation, it is reasonable to retry the operation once. However, repeated failures on the same dataset typically indicate a genuine issue that retrying will not resolve.

### Contact AWS Support

**Open a support case immediately when an upgrade fails**, even if a retry subsequently succeeds. There are several reasons for this:

1. **Root cause analysis.** AWS service teams have visibility into internal engine logs, storage-layer events, and fleet-wide patterns that are not exposed to customers. A support case triggers investigation into whether the failure was caused by a known issue, a data-level problem, or a transient platform event.

2. **Protecting your production upgrade.** If you tested on a snapshot and it failed, AWS Support can advise whether the failure is specific to your data (and thus likely to recur on production) or was transient and safe to proceed past.

3. **Contributing to fleet-wide fixes.** Reporting failures — even ones that resolve on retry — helps AWS identify emerging patterns across the fleet. Your case may be the data point that triggers a broader investigation or patch.

4. **Documenting the event.** A support case creates a permanent record with timestamps, error logs, and AWS-side telemetry. If the same issue recurs weeks later during a production upgrade, having the earlier case dramatically accelerates diagnosis.

When opening the case, include:
- The cluster/instance identifier and region.
- The source and target engine versions.
- The exact timestamp of the failed upgrade attempt.
- Any error messages from the Events console or engine error log.
- Whether a retry succeeded or failed.

Reference: [Creating a support case](https://docs.aws.amazon.com/awssupport/latest/user/case-management.html)

### Logical migration as a fallback

If the upgrade path itself is the problem (the data is incompatible with the in-place physical upgrade mechanism), a logical migration bypasses the storage layer entirely.

**DMS Homogeneous Migration (recommended — fully managed, serverless):**

DMS Homogeneous Migration handles both MySQL and PostgreSQL. It uses native engine tools under the hood (mydumper/myloader + binlog replication for MySQL; pg_dump/pg_restore + logical replication for PostgreSQL) but manages the entire workflow as a serverless operation.

1. Create a fresh target cluster on the desired engine version.
2. Configure a DMS homogeneous migration in "Full load and change data capture (CDC)" mode.
3. DMS performs the initial data load and sets up ongoing replication automatically.
4. Monitor replication lag in the DMS console. Once it reaches zero, stop writes on the source and switch application endpoints.

Expected cutover downtime: 5–15 minutes.

**Self-managed logical migration (if DMS is not suitable):**

For cases where DMS constraints are a problem (e.g. network isolation, unsupported extensions, or need for fine-grained control over the process):

- **MySQL:** mydumper/myloader for initial load, then binlog replication.
- **PostgreSQL:** `pg_dump`/`pg_restore` (parallel mode with `-j`) for initial load, then native logical replication:
   ```sql
   -- On source (requires rds.logical_replication = 1):
   CREATE PUBLICATION upgrade_pub FOR ALL TABLES;

   -- On target:
   CREATE SUBSCRIPTION upgrade_sub
     CONNECTION 'host=source-endpoint dbname=mydb user=repl_user password=...'
     PUBLICATION upgrade_pub;
   ```

**Important PostgreSQL considerations (applies to both DMS and self-managed):**

- Logical replication does not replicate DDL or sequence values. Run `SELECT setval()` on target sequences before cutover.
- Large objects (`lo` type) are not replicated by native logical replication. Use `pg_dump` with `--large-objects` for the initial load.
- Extensions must be pre-installed on the target at compatible versions. Check with `SELECT * FROM pg_extension;` on both source and target.

References:
- [Migrating MySQL databases with homogeneous data migrations](https://docs.aws.amazon.com/dms/latest/userguide/dm-migrating-data-mysql.html)
- [Migrating PostgreSQL databases with homogeneous data migrations](https://docs.aws.amazon.com/dms/latest/userguide/dm-migrating-data-postgresql.html)
- [Multi-threaded migration using mydumper and myloader](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-large-mysql-mariadb-databases/mydumper.html)
- [Logical replication for Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.html)
- [Performing a major version upgrade for Aurora PostgreSQL using logical replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.Logical.html#AuroraPostgreSQL.Replication.Logical.MajorUpgrade)



## Connection resilience during upgrades

### RDS Proxy

Deploying RDS Proxy before an upgrade reduces application-perceived downtime during switchover or failover events:

- Internal benchmarks show RDS Proxy reduces client recovery time after Aurora MySQL failover by up to 79%, with average failover times of approximately 3 seconds (vs ~14 seconds with optimised direct connections, or ~24 seconds with default driver settings).
- Idle connections are preserved transparently through the failover.
- Active in-flight transactions are terminated to allow fast retry.

RDS Proxy is fully managed, multi-AZ, and requires no operational overhead beyond configuration.

References:
- [Improving application availability with Amazon RDS Proxy](https://aws.amazon.com/blogs/database/improving-application-availability-with-amazon-rds-proxy/)
- [Using Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy.html)
- [RDS Proxy pricing](https://aws.amazon.com/rds/proxy/pricing/)

### Application-side connection handling

Regardless of whether you use RDS Proxy, applications should implement:

- **Connection validation on checkout** — test connections before use (most connection pools support this).
- **Retry logic with backoff** — transient connection errors during failover should trigger automatic retry, not application failure.
- **Short connection timeouts** — avoid holding stale connections for minutes while waiting for TCP timeout detection.



## Ongoing monitoring and maintenance

1. **Periodic backup restore testing.** Schedule regular test-restores of automated snapshots to verify they start cleanly. AWS Backup Restore Testing can automate this.
   - Reference: [AWS Backup Restore Testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)

2. **Monitor engine health.** For MySQL: periodically check `SHOW ENGINE INNODB STATUS` and engine error logs for assertion warnings or storage anomalies. For PostgreSQL: monitor `pg_stat_bgwriter`, `pg_stat_database`, `pg_stat_activity` (long-running transactions and idle-in-transaction sessions), and the PostgreSQL error log. Run `ANALYZE` on tables after a major version upgrade — the new version's statistics are rebuilt from scratch by `pg_upgrade` with `--analyze-in-stages` but may need additional passes under production load.

3. **Enable Enhanced Monitoring and Performance Insights** — these surface crash loops, replication lag spikes, and performance degradation early.
   - Reference: [Enhanced Monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_Monitoring.OS.html)
   - Reference: [Performance Insights](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_PerfInsights.html)

4. **Stay on LTS releases where possible.** For Aurora MySQL, LTS versions receive patches for longer and are the automatic upgrade target for end-of-support versions. For Aurora PostgreSQL, LTS designations apply similarly — check the release calendars for your engine. For RDS for PostgreSQL, track the upstream PostgreSQL community end-of-life dates; AWS standard support typically extends ~3 years beyond the community EOL, but extended support incurs additional charges.

5. **Subscribe to RDS event notifications** for maintenance windows, version deprecation announcements, and hardware lifecycle events.
   - Reference: [Using Amazon RDS event notification](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Events.html)



## Summary checklist

| Phase | Action |
|-------|--------|
| Planning | Identify target version (prefer LTS) |
| Planning | Check end-of-support dates for current version |
| Planning | Review pre-upgrade checks and incompatibility reports |
| Planning | (PostgreSQL) Update/drop incompatible extensions, resolve orphaned objects, drop replication slots |
| Testing | Restore production snapshot to isolated environment |
| Testing | Apply upgrade to the snapshot restore |
| Testing | Validate application connectivity against upgraded instance |
| Execution | Deploy RDS Proxy (if not already in place) |
| Execution | Use Blue/Green Deployment for production |
| Execution | Monitor Events console and engine logs during upgrade |
| Recovery | If upgrade fails: open AWS Support case immediately |
| Recovery | If upgrade fails: retry once if error is not data-specific |
| Recovery | If upgrade path is broken: use logical migration (DMS or native tools) |
| Post-upgrade | Validate application functionality |
| Post-upgrade | (PostgreSQL) Run ANALYZE on all databases to rebuild planner statistics |
| Post-upgrade | Monitor performance baselines for regression |
| Post-upgrade | Update monitoring alerts for new version metrics |
