# Database Migration Paths

RDS to Aurora migration, cross-account MariaDB/MySQL migration, PostgreSQL version upgrades.


## 8. RDS to Aurora migration paths

### Option A: Snapshot migration (fastest)

1. Create snapshot of RDS PostgreSQL
2. Migrate snapshot directly to Aurora PostgreSQL (can upgrade version in same operation)
3. Update application connection string
4. Keep original RDS as backup for 24-48 hours

When restoring from snapshot, you can upgrade the version in a single operation. The restore process runs upgrade prechecks automatically.

Downtime: 30-60 minutes (snapshot creation + Aurora restore).

### Option B: Aurora read replica (minimal downtime)

1. Upgrade RDS to target PostgreSQL version first
2. Create Aurora read replica from upgraded RDS
3. Wait for replication lag = 0
4. Promote Aurora read replica

Constraint: Aurora read replicas must be the same major version as the source RDS instance. For cross-version migration, upgrade RDS first.

Downtime: 1-2 minutes (promotion).

### Important considerations

- Unlogged tables are not replicated to Aurora read replica; must be manually recreated after promotion
- Check for unlogged tables: `SELECT schemaname, tablename FROM pg_tables WHERE relpersistence = 'u';`
- Keep source RDS running until Aurora validated
- Take snapshot of Aurora immediately after promotion

References:
- [Migrating data to Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Migrating.html)
- [Migration using Aurora read replica](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Migrating.RDSPostgreSQL.Replica.html)
- [Migration using snapshot](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Migrating.RDSPostgreSQL.Import.Console.html)
- [Restoring from a DB cluster snapshot](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-restore-snapshot.html)


## 9. Cross-account RDS MariaDB/MySQL migration

### Recommended approach: snapshot + binlog replication

This is the official AWS-recommended method for cross-account RDS migration. It avoids DMS limitations with MyISAM tables, LOB columns without primary keys, generated columns, and partitioned tables.

### Why DMS is problematic for MyISAM workloads

- DMS CDC requires primary keys or unique constraints to track changes
- Adding primary keys to live MyISAM tables takes exclusive write locks (table-level locking)
- DMS full load uses mydumper with `FLUSH TABLES WITH READ LOCK`, blocking writes during dump
- DMS cannot replicate generated columns directly
- DMS won't recreate partition structures

### Binlog replication advantages

- No primary keys required
- No schema modifications needed
- Generated columns auto-calculated from base column changes
- Partition structures included in snapshot
- LOB/BLOB columns replicate normally

### Implementation steps

Note: MySQL 8.0.23+ uses SOURCE/REPLICA terminology. For older versions, use the legacy commands shown in parentheses. RDS procedure names (`mysql.rds_set_external_master`, `mysql.rds_start_replication`) are fixed API names and cannot be renamed.

1. Enable binlog retention on source: `CALL mysql.rds_set_configuration('binlog retention hours', 72);`
2. Create replication user with `REPLICATION REPLICA` privileges (or `REPLICATION SLAVE` on MySQL < 8.0.23)
3. Capture binlog position: `SHOW BINARY LOG STATUS;` (or `SHOW MASTER STATUS;` on MySQL < 8.0.23)
4. Take snapshot immediately after capturing position
5. Share snapshot cross-account (share KMS key if encrypted)
6. Restore snapshot in target account
7. Configure replication on target:
   ```sql
   CALL mysql.rds_set_external_master(
     '<source_endpoint>', 3306, 'repl_user', '<password>',
     '<binlog_file>', <position>, 0
   );
   CALL mysql.rds_start_replication();
   ```
8. Monitor: `SHOW REPLICA STATUS\G` (or `SHOW SLAVE STATUS\G` on MySQL < 8.0.23). Check the `Seconds_Behind_Source` (or `Seconds_Behind_Master`) replication lag column.
9. Cutover: Stop writes, wait for sync, stop replication, switch application

### GTID note

GTID-based replication is not supported with MyISAM tables. Use binary log position-based replication.

### Network connectivity

Requires VPC Peering or Transit Gateway between accounts. Security groups must allow MySQL/MariaDB traffic (port 3306). Enable SSL for the replication connection after configuring external replication:

```sql
CALL mysql.rds_stop_replication;
CALL mysql.rds_set_external_master_with_auto_position(
  '<source_endpoint>', 3306, 'repl_user', '<password>', 1
);
CALL mysql.rds_start_replication;
```

Alternatively, if using binlog position-based replication, add SSL after step 7:

```sql
-- MySQL 8.0.23+ (recommended):
STOP REPLICA;
CHANGE REPLICATION SOURCE TO SOURCE_SSL=1;
START REPLICA;

-- MySQL < 8.0.23 (legacy):
STOP SLAVE;
CHANGE MASTER TO MASTER_SSL=1;
START SLAVE;
```

References:
- [AWS Support Knowledge Center - Cross-Account RDS MySQL Migration](https://aws.amazon.com/premiumsupport/knowledge-center/rds-mysql-cross-region-replica/)
- [MySQL GTID Restrictions](https://docs.oracle.com/cd/E17952_01/mysql-8.0-en/replication-gtids-restrictions.html)


## 10. PostgreSQL version upgrade considerations

### 13 to 14 (safe)

- Django 5.1 supports PostgreSQL 13+; Django 4.2 LTS supports PostgreSQL 12+
- No breaking changes affecting Django applications
- Recommended to avoid extended support costs

### 13 to 17 (not recommended without thorough testing)

Breaking changes in PostgreSQL 17:
- `search_path` changes: Functions in expression indexes and materialised views must explicitly specify search paths
- Interval parsing: `ago` keyword only allowed at end of interval values
- `old_snapshot_threshold` removed
- System catalogue renames: pg_stat views have renamed columns (raw SQL queries against these views will break)
- Maintenance function behaviour changes for ANALYZE, CLUSTER, CREATE INDEX, REINDEX, VACUUM

Testing requirements: All custom SQL queries, expression indexes with custom functions, third-party package compatibility.

References:
- [PostgreSQL 17 Release Notes](https://www.postgresql.org/docs/current/release-17.html)
- [Django Databases](https://docs.djangoproject.com/en/5.1/ref/databases/)
