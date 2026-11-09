# Meta DWH Data Model

This document describes the schema design, table granularities, relationships, and design assumptions for the Meta Data Warehouse (Trino & Iceberg Usage Analytics).

## 1. Schema Overview

The model follows a Star Schema extended with a Bridge Table to resolve the Many-to-Many (N:M) relationship between queries and referenced tables, and an SCD Type 2 structure for organizational memberships.

```text
                  +---------------------+
                  |      dim_teams      |
                  +---------------------+
                             |
                             | 1:N
                             v
+-------------------+     +---------------------+
|     dim_users     |---->| user_team_membership|
+-------------------+ 1:N +---------------------+
          |                          |
          | 1:N                      | 1:N (point-in-time)
          v                          v
+-----------------------------------------------+
|                  fact_queries                 |
+-----------------------------------------------+
                        |
                        | 1:N
                        v
+-----------------------------------------------+
|              bridge_query_tables              |
+-----------------------------------------------+
                        ^
                        | N:1
+-----------------------------------------------+
|                  dim_tables                   |
+-----------------------------------------------+
```

---

## 2. Table Specifications & Granularity

### `fact_queries`
* **Granularity:** One row per query execution.
* **Primary Key:** `query_id`
* **Foreign Keys:** `user_id` -> `dim_users(user_id)`, `team_id` -> `dim_teams(team_id)`
* **Description:** Contains execution metrics, runtime, timestamps, and resource consumption counters for each query run on Trino.
* **Attributes:**
  * `query_id` (VARCHAR, PK): Unique query execution identifier.
  * `user_id` (VARCHAR): Identifier of the user who executed the query.
  * `team_id` (VARCHAR): Resolved at query runtime based on `user_team_membership`.
  * `started_at` (TIMESTAMP): Query start timestamp.
  * `event_date` (DATE): Query execution date, used for partitioning.
  * `state` (VARCHAR): Final state (`FINISHED`, `FAILED`, `CANCELED`).
  * `duration_ms` (BIGINT): Wall-clock execution time in milliseconds.
  * `cpu_ms` (BIGINT): Aggregate CPU time across all workers.
  * `physical_input_bytes` (BIGINT): Bytes read from storage (S3/Iceberg).
  * `peak_memory_bytes` (BIGINT): Maximum memory reserved during execution.
  * `spilled_bytes` (BIGINT): Data spilled to disk when memory limits are exceeded.

### `bridge_query_tables`
* **Granularity:** One row per query-table access.
* **Primary Key:** `(query_id, table_id)`
* **Foreign Keys:** `query_id` -> `fact_queries(query_id)`, `table_id` -> `dim_tables(table_id)`
* **Description:** Resolves the Many-to-Many relationship between queries and Iceberg tables. If a query joins 3 tables, it produces 3 rows in this bridge table.

### `dim_tables`
* **Granularity:** One row per registered Iceberg/Hive table.
* **Primary Key:** `table_id` (e.g., `hive.sales.orders`)
* **Attributes:** `catalog_name`, `schema_name`, `table_name`.

### `dim_users`
* **Granularity:** One row per unique user executing queries.
* **Primary Key:** `user_id`

### `dim_teams`
* **Granularity:** One row per team or department.
* **Primary Key:** `team_id`
* **Includes:** A default fallback record `'unknown'` for unassigned users or system service accounts.

### `user_team_membership` (SCD Type 2)
* **Granularity:** One row per user team assignment period.
* **Primary Key:** `(user_id, team_id, valid_from)`
* **Attributes:** `valid_from` (DATE), `valid_to` (DATE).

---

## 3. Aggregation Tables (Serving / Gold Layer)

Pre-aggregated rollup tables accelerate common dashboard queries and eliminate repeated scans and joins over fact data.

### `agg_daily_table_usage`
* **Granularity:** One row per `(event_date, table_id)`.
* **Metrics:**
  * `query_count`: Total queries hitting the table on that day.
  * `distinct_user_count`: Distinct users interacting with the table on that day.
* **Additivity Note:** `distinct_user_count` represents daily active users. Summing this across multiple days produces "user-days". For distinct users over arbitrary multi-day periods, query `fact_queries` joined with `bridge_query_tables`.

### `agg_daily_team_usage`
* **Granularity:** One row per `(event_date, team_id)`.
* **Metrics:** `query_count`, `cpu_ms`, `physical_input_bytes`, `spilled_bytes`.
* **Additivity:** Fully additive across time and team dimensions.

---

## 4. Modeling Assumptions & Edge Cases

1. **Multi-Table Resource Attribution:**
   * Trino reports resource metrics (`cpu_ms`, `physical_input_bytes`) at the *query level*, not per individual table in a multi-table query.
   * Direct joins between `fact_queries` and `bridge_query_tables` when summing resources would duplicate resource counts. Therefore, resource consumption is attributed to **queries and teams**, while **table analytics** focuses on access frequency, popularity, and user reach.
2. **User Team Assignment Over Time:**
   * A user's team is determined at query execution time (`DATE(started_at) >= valid_from AND DATE(started_at) < valid_to`).
   * If a user transitions across teams, historical queries preserve the team affiliation active at the time of execution.
   * If no membership is found, the query is assigned to `'unknown'`.
3. **Query Deduplication:**
   * `query_id` is unique in Trino. Any duplicate events from pipeline retries are deduplicated using window ranking (`ROW_NUMBER() OVER (PARTITION BY query_id ORDER BY started_at DESC)`).

