# MSSQL to Aurora PostgreSQL Migration

Heterogeneous migration (migration between different database engines) from RDS SQL Server (or on-premises MSSQL) to Aurora PostgreSQL via AWS DMS. Covers data type mappings, case insensitivity strategies, stored procedure refactoring patterns, DMS Schema Conversion, and blob/JSON handling.

**Prerequisites:** This guide is intended for database administrators or developers with SQL Server experience who are planning a migration to PostgreSQL. Familiarity with database concepts like stored procedures, data types, and replication is assumed. New to PostgreSQL? See the [Aurora PostgreSQL documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraPostgreSQL.html).

**Glossary:** CDC = Change Data Capture (ongoing replication of changes). DDL = Data Definition Language (CREATE, ALTER, DROP). DML = Data Manipulation Language (INSERT, UPDATE, DELETE). DMS = AWS Database Migration Service. DMS SC = DMS Schema Conversion. LOB = Large Object (BLOB, CLOB). PL/pgSQL = PostgreSQL's built-in procedural language for stored functions. UAT = User Acceptance Testing.


## 1. Migration strategy overview

MSSQL→PostgreSQL is a heterogeneous migration requiring schema conversion, data type mapping, and application code adjustments. The recommended tooling:

| Phase | Tool | Purpose |
|-------|------|---------|
| Schema assessment | DMS Schema Conversion (DMS SC) | Automated complexity analysis and DDL generation |
| Schema creation | DMS SC output + manual review | Target schema deployment |
| Data migration | AWS DMS (full-load + CDC) | Bulk data transfer and replication until cutover |
| Stored procedure conversion | Manual refactoring | PL/pgSQL rewrite |
| Validation | DMS data validation + custom queries | Row counts, data integrity |


## 2. Data type mappings

| MSSQL | PostgreSQL | Notes |
|-------|-----------|-------|
| `uniqueidentifier` | `UUID` | Direct mapping |
| `bigint` | `BIGINT` | Direct |
| `int` | `INTEGER` | Direct |
| `nvarchar(n)` | `VARCHAR(n)` | PostgreSQL is UTF-8 native; no `N` prefix needed |
| `nvarchar(MAX)` | `TEXT` | Unlimited length |
| `varchar(MAX)` | `TEXT` | Unlimited length |
| `tinyint` | `SMALLINT` | See range enforcement below |
| `bit` | `BOOLEAN` | `1`/`0` → `TRUE`/`FALSE` |
| `float` / `float(53)` | `DOUBLE PRECISION` | 8-byte IEEE 754 |
| `float(24)` | `REAL` | 4-byte IEEE 754 |
| `decimal(p,s)` | `NUMERIC(p,s)` | Direct |
| `datetime` | `TIMESTAMP(3)` | 3.33 ms precision equivalent |
| `datetime2` | `TIMESTAMP(6)` | Microsecond precision |
| `datetimeoffset` | `TIMESTAMPTZ` | Timezone-aware |
| `IDENTITY(1,1)` | `GENERATED ALWAYS AS IDENTITY` | Auto-increment |
| `varbinary(MAX)` | `BYTEA` | Binary data |
| `xml` | `XML` | Direct (limited XQuery in PG) |

### tinyint range enforcement

MSSQL `tinyint` is 0-255. PostgreSQL has no unsigned integer type. Three options:

```sql
-- Option 1: Direct (allows negative values — acceptable if app never writes negatives)
Status SMALLINT NOT NULL

-- Option 2: CHECK constraint (enforces MSSQL range)
Status SMALLINT NOT NULL CHECK (Status >= 0 AND Status <= 255)

-- Option 3: Reusable domain
CREATE DOMAIN tinyint AS SMALLINT CHECK (VALUE >= 0 AND VALUE <= 255);
Status tinyint NOT NULL
```

Option 2 is recommended for tables where the 0-255 range is semantically meaningful.


## 3. Case insensitivity

MSSQL uses case-insensitive collation by default (`SQL_Latin1_General_CP1_CI_AS`). PostgreSQL is case-sensitive by default. Two strategies:

### Option 1: citext extension (recommended for most cases)

```sql
CREATE EXTENSION IF NOT EXISTS citext;

-- Use for columns that need case-insensitive comparison
CREATE TABLE users (
    email CITEXT NOT NULL,
    username CITEXT NOT NULL
);
```

Advantages: transparent to application code, works with indexes, `LIKE`/`=` comparisons are case-insensitive automatically.

Limitation: applies to the entire column — cannot mix case-sensitive and case-insensitive queries on the same column.

### Option 2: ICU collation (PostgreSQL 12+)

```sql
CREATE COLLATION case_insensitive (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);

-- Apply per column
Name VARCHAR(100) COLLATE case_insensitive
```

Advantages: more granular control, no extension dependency.

Limitation: non-deterministic collations cannot be used with `UNIQUE` constraints or as hash join keys without additional handling.

### Recommendation

Use `citext` for columns that need case-insensitive equality and LIKE operations (email, username, name fields). Use ICU collation only when you need locale-aware sorting behaviour.


## 4. Stored procedure refactoring patterns

MSSQL stored procedures must be rewritten as PostgreSQL functions using PL/pgSQL. DMS Schema Conversion handles 40-60% of procedures automatically; the rest require manual refactoring.

### Key syntax changes

| MSSQL | PostgreSQL | Example |
|-------|-----------|---------|
| `NVARCHAR` | `VARCHAR` | Parameters and variables |
| `@variable` | Declared variable (no prefix) | `DECLARE v_name VARCHAR;` |
| `+` (string concat) | `||` | `first_name || ' ' || last_name` |
| `CHAR(13) + CHAR(10)` | `E'\r\n'` | Line breaks |
| `= 1` (boolean) | `= TRUE` | Bit-to-boolean conversion |
| `BEGIN...END` (procedure) | `$$...$$` with `LANGUAGE plpgsql` | Dollar-quoting |
| `OUTPUT` parameters | `OUT` parameters or `RETURNS TABLE` | Return values |
| `EXEC sp_name` | `PERFORM function_name()` or `SELECT function_name()` | Calling functions |
| `@@ROWCOUNT` | `GET DIAGNOSTICS row_count = ROW_COUNT` | Affected rows |
| `@@IDENTITY` | `currval('sequence_name')` | Last inserted ID |
| `ISNULL(x, default)` | `COALESCE(x, default)` | Null handling |
| `GETDATE()` | `NOW()` or `CURRENT_TIMESTAMP` | Current timestamp |
| `TOP n` | `LIMIT n` | Row limiting |
| `NOLOCK` hint | Remove entirely | PG uses MVCC; no dirty reads |

### Critical differences to watch

- **`SELECT INTO` behaviour**: In MSSQL, `SELECT INTO` creates a new table. In PL/pgSQL, `SELECT INTO` assigns to a variable. Use `CREATE TABLE AS SELECT` for table creation.
- **NULL handling in concatenation**: MSSQL ignores NULLs in `+` concatenation (with `CONCAT_NULL_YIELDS_NULL OFF`). PostgreSQL `||` returns NULL if any operand is NULL. Use `COALESCE()`.
- **Multi-row SELECT INTO**: PL/pgSQL raises an error if `SELECT INTO` returns multiple rows. Add `LIMIT 1` or use a cursor.
- **Temporary tables**: MSSQL `#temp` tables → PostgreSQL `CREATE TEMP TABLE` (dropped at session end by default).
- **Error handling**: `TRY...CATCH` → `BEGIN...EXCEPTION WHEN...END` blocks.


## 5. DMS Schema Conversion (DMS SC)

### What it does

DMS SC analyses source MSSQL objects and generates PostgreSQL DDL automatically. It produces:
- Conversion complexity score per database (Simple/Medium/Complex)
- Object-level feasibility percentages
- Action items list for objects requiring manual intervention
- Estimated effort per object type

### Typical auto-conversion rates

| Object type | Auto-convertible | Manual required |
|-------------|-----------------|-----------------|
| Tables | 95%+ | 5% (custom types, computed columns) |
| Indexes | 90% | 10% (filtered indexes, included columns) |
| Stored procedures | 40-60% | 40-60% (complex logic, cursors, dynamic SQL) |
| Views | 80% | 20% (nested views, recursive CTEs) |
| Constraints | 95%+ | Rare |

### Known DMS SC limitations

- Does NOT convert: application code, connection strings, ORM configurations
- Partial conversion only: procedures with cursors, dynamic SQL, temp tables
- Manual review required: triggers with business logic, nested views, recursive CTEs
- Data type nuances: `tinyint` range enforcement, `datetime` precision, `IDENTITY` gaps

### Workflow

1. Create DMS SC project and connect to source MSSQL
2. Run assessment (generates feasibility report)
3. Review action items — categorise as blocker/high/medium/low
4. Execute auto-conversion for supported objects
5. Manually address action items
6. Validate output against application requirements


## 6. Blob and JSON data handling

DMS has known difficulties with large binary and JSON columns. Performance issues and data corruption risks increase with these types.

### Recommendations

**JSON columns**: Consider migrating to PostgreSQL's native `JSONB` type (supports indexing via GIN). Alternatively, if the JSON data is heavily queried, evaluate whether DocumentDB or DynamoDB is a better fit. DMS can replicate JSON as `TEXT` or `JSONB`, but large JSON documents may cause replication lag.

**Binary/blob columns** (images, videos, PDFs): 

- Configure DMS LOB settings explicitly: choose Full LOB mode or Limited LOB mode with an appropriate `LobMaxSize`
- Test blob replication in a non-production environment before go-live
- Verify target column storage capacity and data type mapping (`varbinary(MAX)` → `BYTEA`)
- Monitor DMS instance memory during blob-heavy replication phases
- Consider offloading large blobs to S3 with a pointer in the database (long-term architectural improvement)

### DMS task configuration for LOBs

Exclude blob-heavy tables from the main DMS task and replicate them in a separate task with:
- Larger DMS instance class (r5.xlarge+)
- `LobMaxSize` set to accommodate the largest expected blob
- Lower `CommitRate` to avoid memory pressure


## 7. DMS data replication configuration

### Full-load settings

```json
{
  "FullLoadSettings": {
    "TargetTablePrepMode": "DROP_AND_CREATE",
    "MaxFullLoadSubTasks": 8,
    "TransactionConsistencyTimeout": 600,
    "CommitRate": 10000
  }
}
```

- `MaxFullLoadSubTasks`: Parallelism for initial load. Set based on source IOPS capacity.
- `CommitRate`: Rows per commit batch. Higher = faster but more memory.

### CDC settings

- Enable CDC after full load completes (DMS handles this automatically with full-load + CDC task type)
- Monitor `CDCLatencySource` and `CDCLatencyTarget` in CloudWatch
- Target replication lag < 10 seconds before cutover

### Table mapping rules

```json
{
  "rules": [
    {
      "rule-type": "selection",
      "rule-id": "1",
      "rule-name": "include-schema",
      "object-locator": {
        "schema-name": "dbo",
        "table-name": "%"
      },
      "rule-action": "include"
    },
    {
      "rule-type": "selection",
      "rule-id": "2",
      "rule-name": "exclude-blob-tables",
      "object-locator": {
        "schema-name": "dbo",
        "table-name": "documents"
      },
      "rule-action": "exclude"
    }
  ]
}
```


## 8. Cutover strategy

1. **Pre-cutover**: Confirm DMS replication lag < 10 seconds, run data validation (row counts, checksums)
2. **Cutover window**: Stop writes to MSSQL, wait for CDC to drain (lag = 0), switch application connection strings to Aurora PostgreSQL
3. **Rollback safety**: Keep MSSQL in read-only mode for 48+ hours after cutover
4. **Post-cutover**: Monitor application performance, validate critical business workflows, run integrity checks

### Connection string switching

Use feature flags or configuration management to switch database targets without redeployment. DNS-based switching (CNAME flip) works for connection-string-only changes.


## 9. Risk mitigation

| Risk | Mitigation |
|------|-----------|
| Stored procedure logic errors | Unit test each refactored function; run parallel execution against both databases during UAT |
| DMS replication lag | Monitor lag continuously; increase instance size if lag grows |
| Data type mismatch | Validate DMS SC type mappings against application expectations in UAT |
| Blob/JSON migration failure | Exclude from main DMS task; migrate separately with dedicated instance |
| Application compatibility | Maintain MSSQL in read-only standby; instant rollback via connection string switch |
| Case sensitivity breakage | Audit all string comparison queries; apply `citext` to columns identified as case-insensitive |


## 10. Post-migration considerations

- **Performance tuning**: PostgreSQL query planner differs from MSSQL. Review execution plans for critical queries. `pg_stat_statements` helps identify slow queries.
- **Index strategy**: MSSQL filtered indexes and included columns don't map 1:1. Review index usage after migration; PostgreSQL partial indexes serve a similar role to filtered indexes.
- **Connection pooling**: If the application used MSSQL connection pooling heavily, consider PgBouncer or RDS Proxy for Aurora PostgreSQL.
- **Monitoring**: Set up Performance Insights, CloudWatch alarms for CPU/memory/connections, and `pg_stat_statements` for query-level visibility.
