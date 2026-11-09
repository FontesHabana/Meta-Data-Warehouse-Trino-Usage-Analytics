# Meta DWH Architecture & Ingestion Design

This document outlines the production architecture, data pipeline lifecycle, incremental backfill mechanics, and infrastructure design choices for tracking Trino and Apache Iceberg usage.

---

## 1. End-to-End Pipeline Architecture

```text
[ Trino Cluster ]
       |
       | (Trino EventListener Plugin)
       v
[ AWS S3 / Kafka ] (Raw JSON / Parquet query events)
       |
       | Incremental Micro-batch / Daily Batch
       v
[ Staging / Bronze Layer ] (Raw Iceberg tables)
       |
       | Transformation & Deduplication (DuckDB / dbt / Spark)
       v
[ Meta DWH / Silver Layer ]
   ├── fact_queries
   ├── bridge_query_tables
   └── Dimension Tables (dim_tables, dim_users, dim_teams)
       |
       | Aggregation Layer (Gold)
       v
[ Aggregates / Gold Layer ]
   ├── agg_daily_table_usage
   └── agg_daily_team_usage
       |
       v
[ BI Dashboards & Product Analytics ]
```

### Data Extraction from Trino
Trino provides an internal SPI called `EventListener`. A custom listener captures:
* `QueryCompletedEvent`: Emitted as soon as a query finishes or fails.
* Extracted payloads include: `queryId`, `user`, `source`, `queryStats` (CPU time, wall time, peak memory, input bytes), and `ioMetadata` (the list of inputs/tables read with catalog, schema, and table names).

---

## 2. Idempotency & Incremental Loading Strategy

To support backfills, historical recalculations, and late-arriving events without generating duplicate metrics:

1. **Partition Replacement Strategy:**
   * The fact table and aggregate tables are partitioned by `event_date`.
   * For incoming data batches, the pipeline:
     1. Identifies distinct `event_date` values in the batch.
     2. Deletes existing entries for incoming `query_id`s from `bridge_query_tables` and `fact_queries`.
     3. Inserts deduplicated facts.
     4. Atomically recalculates and overwrites aggregates only for the affected dates:
        ```sql
        DELETE FROM agg_daily_team_usage 
        WHERE event_date IN (SELECT DISTINCT event_date FROM affected_dates);

        INSERT INTO agg_daily_team_usage ...;
        ```
2. **Deterministic Upserts for Dimensions:**
   * Dimension tables (`dim_tables`, `dim_users`, `dim_teams`) use `INSERT ... WHERE NOT EXISTS` or `ON CONFLICT DO NOTHING` semantics to ensure new entities are registered without corrupting existing records.

---

## 3. Resource Usage Metrics Justification

To provide actionable insights into cluster utilization and cost, we track four primary resource metrics:

| Metric | Business & Engineering Value |
| :--- | :--- |
| **`cpu_ms`** | Measures actual computational work. In cloud environments (e.g., EMR, EKS), CPU utilization directly dictates cluster autoscaling and compute costs. |
| **`physical_input_bytes`** | Measures storage I/O bandwidth and S3 data scans. Essential for evaluating partition pruning efficiency and table compaction strategies. |
| **`peak_memory_bytes`** | Essential for capacity planning and detecting memory-intensive queries that risk cluster Out-Of-Memory (OOM) errors. |
| **`spilled_bytes`** | Direct indicator of query inefficiency. Spilling occurs when memory limits are exceeded and intermediate data writes to local disk, degrading cluster performance. |

---

## 4. Production Recommendations for Iceberg Metadata

In an enterprise Trino + Iceberg environment, query access logs can be cross-referenced with **Iceberg System Metadata Tables**:
* `<table>$snapshots`: Track the precise snapshot version read by each query.
* `<table>$partitions`: Determine if queries are performing full scans or effectively utilizing partition pruning.
* Integrating Iceberg metadata enables automated detection of unused/abandoned tables, optimization of file compaction, and targeted table cleanup policies.
