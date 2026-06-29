# Oracle to Amazon RDS for Oracle Migration via AWS DMS

DMS CDC replication from on-premises Oracle to Amazon RDS for Oracle. Covers LogMiner vs BinaryReader selection, RAC compatibility, Data Guard integration, LOB handling, bandwidth optimisation, and selective table replication.

**Glossary:** ASM = Automatic Storage Management (Oracle volume manager). CDC = Change Data Capture (ongoing replication of changes after initial load). DML = Data Manipulation Language (INSERT, UPDATE, DELETE). DMS = AWS Database Migration Service. LOB = Large Object (BLOB, CLOB, NCLOB). OLTP = Online Transaction Processing. RAC = Real Application Clusters (Oracle's multi-node clustering). RPO = Recovery Point Objective (maximum acceptable data loss). RTO = Recovery Time Objective (maximum acceptable downtime).


## 1. Architecture overview

AWS DMS captures changes from Oracle redo logs via CDC and replicates them to RDS for Oracle. Two capture methods exist:

- **LogMiner**: Oracle's built-in redo log mining API. Works with Standard and Enterprise Edition. Processes logs locally on the source server.
- **BinaryReader**: Direct binary reading of redo logs. Requires Enterprise Edition. Lower overhead than LogMiner.

Both methods process logs on the source database server. Only filtered change data traverses the network — archive logs are never uploaded to AWS.


## 2. Common misconception: archive log upload

LogMiner does NOT require uploading archive logs to AWS. DMS connects to the Oracle database, uses the LogMiner API to read redo/archive logs locally, filters changes for selected tables/schemas, and transmits only the filtered change data over the network.

Example: 10 GB/hour total redo generation might produce only 100-500 MB/hour of network traffic when replicating a subset of tables.


## 3. LogMiner vs BinaryReader decision matrix

| Factor | LogMiner | BinaryReader |
|--------|----------|--------------|
| Oracle Edition | Standard or Enterprise | Enterprise only |
| Setup complexity | Moderate | Higher |
| Source CPU overhead | Higher | Lower |
| LOB performance | Adequate | Superior |
| Bandwidth efficiency | Baseline | Lower (reads raw redo directly, less metadata overhead) |
| RAC support | Yes | Yes |
| Troubleshooting | Easier (SQL-level) | Harder (binary-level) |
| Oracle licensing impact | None additional | None additional |

### Choose LogMiner when

- Oracle Standard Edition in use
- Simpler setup and maintenance preferred
- Moderate transaction and LOB volumes
- Cost optimisation is priority
- Small to medium RAC clusters (2-4 nodes)

### Choose BinaryReader when

- Oracle Enterprise Edition available
- High-volume LOB replication required
- Bandwidth optimisation is critical (BinaryReader parses compact binary redo directly, reducing I/O vs LogMiner's SQL-based approach)
- Large RAC clusters (4+ nodes) with high transaction volumes
- Performance is the primary concern


## 4. Bandwidth comparison

BinaryReader uses less network bandwidth than LogMiner because it reads and parses raw redo log files directly on the replication instance, avoiding the SQL-layer overhead LogMiner adds (multiple database queries, supplemental log metadata expansion). The difference is workload-dependent — LOB-heavy and high-transaction workloads see a larger gap because LogMiner's per-row metadata overhead scales with row count and LOB size.

AWS recommends BinaryReader when redo generation exceeds 10 GB/hour (single task) or 30 GB/hour (multiple tasks on the same source). Actual throughput depends on network bandwidth between source and replication instance, ASM configuration, and `parallelASMReadThreads`/`readAheadBlocks` settings.

Source: [Using Oracle LogMiner or AWS DMS Binary Reader for CDC](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.Oracle.html#CHAP_Source.Oracle.CDC)


## 5. Selective table replication and bandwidth optimisation

DMS supports schema-level and table-level filtering. When replicating only specific tables, DMS reads all redo logs but discards changes for non-selected tables, so only changes to the filtered table set flow to the target. The bandwidth reduction depends on what proportion of total database activity your selected tables represent — if you replicate 5% of the tables generating 5% of the DML, target-bound traffic drops proportionally.

Example scenario:
```
Total database size: 2 TB
Daily redo generation: 50 GB
Tables to replicate: subset generating ~5-10% of DML
Estimated daily target-bound CDC traffic: proportional to selected table activity
```

Note: DMS still reads the full redo stream on the source side. The filtering reduces target-bound network traffic and target apply load, not source-side I/O.

### Single-task vs multi-task strategy

Use a single DMS task for multiple schemas to avoid redundant redo log processing:

- **Inefficient** (3 separate tasks): Each task processes the full 50 GB redo independently = 150 GB total processing
- **Efficient** (1 task, 3 schemas): Processes redo once = 50 GB total processing

### Row-level filtering

DMS supports column-based filters (e.g., date >= threshold) to further reduce data volume. Apply to tables where historical data is not needed on the target.

### Bandwidth capacity planning

```
Direct Connect bandwidth: 1 Gbps
DMS allocation: 20% = 200 Mbps
Sustainable daily CDC: 200 Mbps x 8 peak hours = 5.76 GB/day
With 50% safety margin: ~2.9 GB/day sustainable
```

Ensure filtered change volume stays below the sustainable threshold.


## 6. Oracle RAC compatibility

Both LogMiner and BinaryReader work with RAC clusters. RAC does NOT require BinaryReader.

### RAC behaviour with DMS

- DMS connects to one RAC node but captures changes from all nodes
- Each RAC instance has its own redo thread; DMS handles multi-thread coordination
- Built-in failover to other RAC nodes if the connected node fails

### RAC-specific best practices

- Connect DMS to the most stable RAC node directly — avoid load balancers
- Enable supplemental logging across all nodes: `ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;`
- Monitor redo generation per node for capacity planning
- Test DMS behaviour during RAC node failures before go-live

### LogMiner vs BinaryReader with RAC

| Aspect | LogMiner + RAC | BinaryReader + RAC |
|--------|----------------|-------------------|
| Oracle Edition | Standard/Enterprise | Enterprise only |
| Performance | Good | Better |
| Resource usage on source | Higher | Lower |
| Failover speed | Standard | Faster |
| Recommended for | 2-4 node clusters | 4+ node clusters |


## 7. Oracle Data Guard integration

DMS works seamlessly with Data Guard environments. Benefits:

- Supplemental logging is already enabled database-wide (Data Guard requirement)
- Archive log retention and backup are already robust
- DMS reads from the primary's archive logs; the standby can be used for initial full load

### Connection strategy

- **CDC**: Connect DMS to the primary database
- **Full load** (optional): Can use the standby to offload read pressure
- **Failover**: DMS handles Data Guard failovers automatically

### Archive log retention for CDC continuity

Sizing formula:
```
Required archive space = (daily_redo / 24) x max_outage_hours x 2 (safety buffer)
Example: (100 GB / 24) x 4 hours x 2 = 33 GB minimum
```

Best practices:
- Maintain 24-48 hours of archive logs minimum (72 hours recommended for high-value migrations)
- Set up CloudWatch alerts for archive log space usage
- Ensure backup jobs don't delete recent archive logs needed by DMS


## 8. LOB handling

LOB columns (BLOB, CLOB, NCLOB) require specific configuration. Two modes:

| Mode | Behaviour | Use when |
|------|-----------|----------|
| Full LOB | Replicates entire LOB regardless of size | Complete data fidelity required |
| Partial LOB | Truncates at configurable limit (default 32 KB) | Performance priority; truncation acceptable |

### Performance impact

- Large LOBs consume significant DMS instance memory
- LOB-heavy workloads may require larger DMS instance classes (r5.xlarge+)
- BinaryReader handles LOBs 40-50% more efficiently than LogMiner

### Mitigation strategies

- Use Partial LOB mode with an appropriate `LobMaxSize` when full fidelity isn't needed
- Size DMS instances for peak LOB throughput, not average
- Monitor memory usage and adjust timeout settings for large objects
- Separate LOB-heavy tables into dedicated DMS tasks if needed


## 9. Pre-migration scoping checklist

Before planning Oracle→RDS for Oracle DMS replication, gather:

**Source database**: Total size, Oracle edition (Standard/Enterprise), version, RAC configuration (node count), archive log mode, supplemental logging status, Data Guard configuration.

**Transaction characteristics**: Redo log generation rate (GB/hour), peak transactions/second, LOB usage and typical sizes, transaction patterns (OLTP/batch/mixed).

**Replication scope**: Which schemas/tables need replication, percentage of total changes that need to replicate, row-level filtering requirements, business-critical tables for priority.

**Network**: Available bandwidth source→AWS, latency to target region, Direct Connect or internet, bandwidth constraints or cost concerns.

**Requirements**: RTO/RPO, acceptable downtime for cutover, CDC continuity tolerance (how long can replication be interrupted before requiring full reload).


## 10. DMS vs Debezium for Oracle migration CDC

DMS CDC is designed for the migration cutover window — it keeps the target in sync with the source until you're ready to switch over. It is not positioned as a long-running continuous replication service.

| Factor | AWS DMS | Debezium Server |
|--------|---------|-----------------|
| Primary use case | Migration cutover (full load + CDC until switch) | Long-running event streaming |
| Management | Fully managed | Self-managed infrastructure |
| Archive log upload | Never (both methods process locally) | Never (uses LogMiner or XStream) |
| AWS integration | Native (CloudWatch, IAM, VPC) | Manual configuration |
| Kafka streaming | Not native (but can target Kinesis) | Native Kafka integration |
| Licensing cost | DMS pricing | Open source (infrastructure cost only) |
| Customisation | Limited to DMS task settings | Full control |

**Choose DMS** when: migrating to RDS/Aurora targets with a defined cutover window, reducing operational overhead during migration.

**Choose Debezium** when: long-running event streaming to Kafka is required beyond the migration window, extensive customisation needed, or on-premises targets.


## 11. Monitoring and troubleshooting

Key DMS metrics to monitor:
- **CDCLatencySource/CDCLatencyTarget**: Replication lag in seconds
- **NetworkTransmitThroughput**: Actual bandwidth consumption
- **MemoryUsage**: Critical for LOB-heavy workloads
- **CDCChangesMemorySource/CDCChangesMemoryTarget**: Change buffer health

Common issues:
- **High memory**: Increase DMS instance size or reduce LOB sizes/batch settings
- **Network timeouts**: Reduce batch size, check Direct Connect stability
- **CDC gap after outage**: Verify archive log retention was sufficient; if not, full reload required
- **RAC failover stall**: Confirm DMS endpoint uses direct node connection, not load balancer
