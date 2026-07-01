# Database Connectivity, Proxies & Read/Write Splitting

RDS Proxy, Heimdall Proxy, Lambda connection patterns, write forwarding (local and cross-region).


## 7. RDS Proxy

### Connection pooling

RDS Proxy provides infrastructure-level connection pooling, preventing connection exhaustion when Lambda functions or microservices scale to hundreds of concurrent executions. Each PostgreSQL connection consumes ~10MB RAM.

### Django compatibility (November 2023 update)

AWS released multiplexing support for PostgreSQL Extended Query Protocol in November 2023. Django's default prepared statements (via psycopg2/psycopg3) now work properly without causing session pinning. No code changes required.

### Operations that cause session pinning

1. `SET` commands (session variables)
2. `PREPARE`, `DISCARD`, `DEALLOCATE`, `EXECUTE` statements (SQL-level, not protocol-level)
3. Creating temporary tables, sequences, or views
4. Declaring cursors
5. Loading library modules
6. Manipulating sequences with `nextval`/`setval`
7. Advisory locks (except transaction-level)
8. Statements over 16 KB

### Best practices

- Move session initialisation to RDS Proxy's initialisation query
- Avoid `SET` statements in application code
- Monitor `DatabaseConnectionsCurrentlySessionPinned` in CloudWatch
- RDS Proxy supports IAM authentication for client connections
- Uses Secrets Manager credentials for database connections

### RDS Proxy with Serverless v2

Supported. Provides connection pooling during ACU scaling events, reduced connection overhead, prevention of connection storms, up to 66% faster failover. Pricing is separate from ACU costs (charged per vCPU-hour).

Note: RDS Proxy prevents auto-pause (maintains persistent connections).

References:
- [Using Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html)
- [RDS Proxy concepts](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html)
- [Avoiding pinning](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-pinning.html)
- [RDS Proxy multiplexing for PostgreSQL Extended Query Protocol](https://aws.amazon.com/blogs/database/amazon-rds-proxy-multiplexing-support-for-postgresql-extended-query-protocol/)


## 17. Heimdall Proxy for read/write splitting

Third-party solution (AWS Marketplace) for automatic read/write routing:

- Application connects to single endpoint
- Reads automatically routed to replicas when safe
- Tracks replica lag to prevent stale reads
- Sends reads to writer when replica lag would cause inconsistency
- No application changes required
- Cost: ~$700-800/month licence

### Advantages over Aurora local write forwarding

- No SQL pattern restrictions: stored procedures, DDL, cursors, SAVEPOINT, COPY, TRUNCATE, sequences, SERIALIZABLE isolation all work because Heimdall routes whole statements to the correct instance rather than forwarding through Aurora's internal mechanism
- Table-level replication lag tracking: tracks last write time per table and routes reads to the writer only for recently-written tables. More granular than write forwarding's SESSION consistency which waits for the entire LSN
- No write latency overhead: writes go directly to the writer, not through a reader-to-writer forwarding path
- Compatible with RDS Proxy (write forwarding is not)
- Additional features: query result caching (ElastiCache), connection pooling with multiplexing, automated failover via RDS API

### Limitations

- Cannot see inside stored procedures or triggers to determine which tables they write to. Procedures must be tagged as write operations in Heimdall's rules. Triggers that write to table B when table A is updated require pg_notify-based invalidation or manual configuration.
- Inline infrastructure component: sits in the data path, requires its own EC2 instances, HA configuration, monitoring, and patching. If Heimdall goes down, database access is lost.
- PostgreSQL-specific restrictions: multi-statement queries are split into individual statements (changes rollback behaviour in auto-commit mode); prepared statements can break multiplexing (may need `preferQueryMode=simple`); runtime `search_path` changes can break cache consistency and read/write split handling.
- Cost: Enterprise Edition ~$2.75/hour for c6g.xlarge. HA pair ~$4,000/month on-demand. Annual contract saves ~32%.

### When to choose Heimdall over write forwarding

- Legacy code uses stored procedures, cursors, savepoints, or DDL through the same connection (write forwarding blockers)
- Write latency matters for individual transactions
- Need query caching or advanced connection pooling
- Already using or planning to use RDS Proxy

### When to choose write forwarding over Heimdall

- Legacy code uses only plain DML (INSERT, UPDATE, DELETE, SELECT)
- Want zero additional infrastructure
- Cost sensitivity (write forwarding is free)
- Low write volume where the forwarding latency overhead is acceptable

References:
- [Heimdall Proxy Enterprise Edition - AWS Marketplace](https://aws.amazon.com/marketplace/pp/B085S2Q91S)
- [Using Heimdall Proxy to split reads and writes for Aurora and RDS](https://aws.amazon.com/blogs/apn/using-the-heimdall-proxy-to-split-reads-and-writes-for-amazon-aurora-and-amazon-rds/)
- [Offloading SQL for Amazon RDS using Heimdall Proxy](https://aws.amazon.com/blogs/architecture/offloading-sql-for-amazon-rds-using-the-heimdall-proxy/)
- [Using Aurora Global Database for low latency without application changes](https://aws.amazon.com/blogs/architecture/using-amazon-aurora-global-database-for-low-latency-without-application-changes/)

### Heimdall with Aurora Global Database (cross-region)

An AWS Architecture Blog post describes deploying Heimdall proxies per region in front of an Aurora Global Database. Heimdall uses latency-based routing (via Route 53) to direct reads to the nearest regional reader and writes to the global writer. It detects failover automatically using the Global Database ARN.

This pattern suits "same database replicated everywhere" — low-latency reads in every region with a single write region. It does not suit data residency architectures where regional data must stay regional.

Heimdall is a connection router, not a query federation engine. It routes entire queries to one cluster. It cannot split a single query across two clusters. A JOIN between a global table and a regional table is impossible through Heimdall — both tables must exist in the same cluster. For architectures with separate global and regional clusters, FDWs or pglogical replication are required to enable cross-cluster JOINs. Heimdall only adds value in this scenario if global data is already replicated locally (via pglogical or Global Database), at which point it's just doing read/write splitting within the regional cluster — something RDS Proxy or application-level routing can handle without the extra infrastructure.


## 18. Lambda database patterns

### Connection pooling in Lambda

Reuse connections across invocations by initialising the pool outside the handler:

Store database credentials in AWS Secrets Manager, not environment variables. RDS Proxy with IAM authentication eliminates password management entirely.

```python
import os, json, psycopg2
from psycopg2 import pool
import boto3

connection_pool = None

def get_secret():
    client = boto3.client('secretsmanager', region_name=os.environ['AWS_REGION'])
    response = client.get_secret_value(SecretId=os.environ['DB_SECRET_ARN'])
    return json.loads(response['SecretString'])

def get_connection_pool():
    global connection_pool
    if connection_pool is None:
        secret = get_secret()
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=5,
            host=secret['host'],
            port=secret['port'],
            database=secret['dbname'],
            user=secret['username'],
            password=secret['password'],
            sslmode='require'
        )
    return connection_pool

def lambda_handler(event, context):
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        # database operations
        cursor.close()
    finally:
        pool.putconn(conn)
```

Keep maxconn low (3-5 per Lambda instance). Total connections = maxconn x concurrent Lambda instances.

### Exponential backoff

```python
import time, random
from psycopg2 import OperationalError

def connect_with_backoff(max_retries=5, base_delay=1, max_delay=32):
    secret = get_secret()
    for attempt in range(max_retries):
        try:
            return psycopg2.connect(
                host=secret['host'], port=secret['port'],
                database=secret['dbname'], user=secret['username'],
                password=secret['password'], sslmode='require',
                connect_timeout=10
            )
        except OperationalError:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            time.sleep(delay + jitter)
```

### Concurrency limits

Set reserved concurrency on Lambda functions to prevent database connection exhaustion.

Calculation:
```
Available connections = max_connections x MaxConnectionsPercent (RDS Proxy)
Safe concurrency = Available connections / connections per Lambda instance
```

Example: 500 max_connections x 90% = 450 available. At 2 connections per Lambda: 225 concurrent Lambdas. Set reserved concurrency to 200 (10% buffer).

References:
- [Managing database connections from Lambda](https://docs.aws.amazon.com/lambda/latest/dg/configuration-database.html)
- [Lambda reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [Error handling and automatic retries](https://docs.aws.amazon.com/general/latest/gr/api-retries.html)


## 25. Aurora PostgreSQL local write forwarding

### What it does

Local write forwarding allows applications to send DML statements (INSERT, UPDATE, DELETE) to an Aurora read replica. The replica forwards those statements to the writer instance over the network. The writer executes them and returns results. This avoids the need to split read and write traffic at the application layer.

Available in Aurora PostgreSQL 14.13+, 15.8+, 16.4+. Enabled at the cluster level, not per-instance.

### When to use it

- Legacy codebases with a single connection that mixes reads and writes, where refactoring to separate writer/reader endpoints is expensive
- Low write volume relative to reads (the documentation describes it as "occasional writes")
- Applications that need read-after-write consistency without complex routing logic
- Replacing connection proxies (pgpool, custom middleware) that route reads and writes

### When not to use it

- Write-heavy workloads where the added latency per write matters
- Applications that rely on stored procedures, user-defined functions, cursors, or DDL through the same connection
- Environments using RDS Proxy (incompatible)
- Applications requiring SERIALIZABLE isolation

### Latency overhead per forwarded write

Each forwarded DML adds network round trips between the reader and writer:

1. Transaction start: ~1.6ms (cross-AZ)
2. DML execution forwarding: ~1.6ms
3. Commit: ~1.6ms
4. Consistency wait (SESSION mode only): the next read in the same session blocks until the write replicates back to the reader — typically 20-100ms depending on replication lag

A single INSERT that takes <1ms directly on the writer takes roughly 5-10ms through forwarding. For a read-after-write pattern (INSERT then SELECT in the same session), total added latency is the forwarding overhead plus the replication wait — roughly 25-110ms.

The overhead is per-transaction latency, not throughput. At low write volumes (hundreds of DML/sec), aggregate throughput impact is negligible.

### Consistency modes

Controlled by the session-level parameter `apg_write_forward.consistency_mode`:

- `SESSION` (default, recommended for most cases): reads after writes in the same session wait for replication. Reads that don't follow a write proceed without waiting.
- `EVENTUAL`: no waiting, reads might return stale data. Lowest latency but defeats read-after-write consistency.
- `GLOBAL`: every read waits for full consistency with the writer, even reads that don't follow a write. Adds latency to all reads. Use only when cross-session consistency is required.
- `OFF`: disables write forwarding for the session.

Only READ COMMITTED and REPEATABLE READ isolation levels are supported. SERIALIZABLE is not.

### Unsupported SQL patterns

These statements fail when executed through a forwarding session:

High risk for legacy codebases:

- User-defined functions and procedures — cannot be called at all through write forwarding
- SAVEPOINT — not supported, and PL/pgSQL exception handling (BEGIN ... EXCEPTION ... END) implicitly creates SAVEPOINTs
- DDL statements (CREATE, ALTER, DROP, etc.)
- Cursors — must be closed before using write forwarding
- Explicit sequence operations — `nextval()` and `setval()` calls fail; implicit sequence usage through SERIAL/IDENTITY column defaults works because the entire INSERT is forwarded

Other unsupported statements: ANALYZE, CLUSTER, COPY, GRANT/REVOKE/REASSIGN OWNED/SECURITY LABEL, LISTEN/NOTIFY, LOCK, SELECT INTO, SET CONSTRAINTS, TRUNCATE, two-phase commit (PREPARE TRANSACTION, COMMIT PREPARED, ROLLBACK PREPARED), VACUUM.

### Connection limits

`apg_write_forward.max_forwarding_connections_percent` (default 25%) caps the percentage of `max_connections` on the writer that can be used for forwarded sessions. Example: if `max_connections` is 800, the writer allows a maximum of 200 simultaneous forwarded sessions.

### Operational considerations

- Not compatible with RDS Proxy.
- Writer restart terminates all active forwarded transactions on readers. Applications need retry logic.
- The internal `rdswriteforwarduser` needs CONNECT privileges on each database. If PUBLIC role CONNECT has been revoked, explicitly GRANT CONNECT to `rdswriteforwarduser`.
- Enabling write forwarding does not require a reboot. Disabling it does not require a reboot either.

### Monitoring

CloudWatch metrics on the writer:

- `AuroraLocalForwardingWriterDMLThroughput` — forwarded DML statements/sec
- `AuroraLocalForwardingWriterOpenSessions` — open forwarded sessions
- `AuroraLocalForwardingWriterTotalSessions` — total forwarded sessions

CloudWatch metrics on each reader:

- `AuroraForwardingReplicaDMLLatency` — average response time of forwarded DMLs (ms)
- `AuroraForwardingReplicaDMLThroughput` — forwarded DML statements/sec
- `AuroraForwardingReplicaReadWaitLatency` — average wait for consistency after writes (ms)
- `AuroraForwardingReplicaCommitThroughput` — commits/sec in forwarded sessions
- `AuroraForwardingReplicaErrorSessionsLimit` — sessions rejected due to max connections limit

Wait events in Performance Insights / Database Insights:

- `IPC:AuroraWriteForwardExecute` — time waiting for forwarded DML to complete on writer
- `IPC:AuroraWriteForwardConsistencyPoint` — time waiting for replication after a write (SESSION/GLOBAL)
- `IPC:AuroraWriteForwardXactCommit` — time waiting for commit confirmation
- `IPC:AuroraWriteForwardXactStart` — time waiting for transaction start on writer
- `IPC:AuroraWriteForwardConnect` — time waiting for connection to writer
- `IPC:AuroraWriteForwardXactAbort` — time waiting for rollback/cleanup after abort

### Adoption checklist

1. Audit application code for unsupported SQL patterns — stored procedures/functions, savepoints, cursors, explicit sequence calls, DDL, COPY.
2. Check that `rdswriteforwarduser` has CONNECT privileges on all databases.
3. Enable on a non-production cluster and run the workload against a reader to identify failures.
4. Use SESSION consistency mode unless there's a reason not to.
5. Add retry logic for writer restart scenarios.
6. Set up CloudWatch metrics and wait event monitoring before production.
7. If the audit reveals heavy use of stored procedures or cursors, write forwarding won't be a drop-in replacement — those code paths still need direct writer access.

References:
- [Local write forwarding in Aurora PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-postgresql-write-forwarding.html)
- [Limitations and considerations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-postgresql-write-forwarding-limitations.html)
- [Configuring local write forwarding](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-postgresql-write-forwarding-configuring.html)
- [Working with local write forwarding](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-postgresql-write-forwarding-understanding.html)
- [Monitoring local write forwarding](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-postgresql-write-forwarding-monitoring.html)
