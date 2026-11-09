
-- 1. How many distinct users queried a specific table
-- during a given period?

SELECT
    b.table_id,
    COUNT(DISTINCT f.user_id) AS distinct_users
FROM fact_queries f
JOIN bridge_query_tables b
    ON f.query_id = b.query_id
WHERE b.table_id = 'hive.sales.orders'
  AND f.event_date BETWEEN DATE '2026-10-01'
                       AND DATE '2026-10-03'
GROUP BY b.table_id;


-- 2. How many queries and how many distinct users
-- accessed each table during a period?

SELECT
    b.table_id,
    COUNT(DISTINCT f.query_id) AS total_queries,
    COUNT(DISTINCT f.user_id) AS total_unique_users
FROM fact_queries f
JOIN bridge_query_tables b ON f.query_id = b.query_id
WHERE f.event_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-03'
GROUP BY b.table_id
ORDER BY total_queries DESC;


-- 3. How many resources did each team consume?

SELECT
    team_id,
    SUM(query_count) AS total_queries,
    SUM(cpu_ms) AS total_cpu_ms,
    SUM(physical_input_bytes) AS total_input_bytes,
    SUM(spilled_bytes) AS total_spilled_bytes
FROM agg_daily_team_usage
WHERE event_date BETWEEN DATE '2026-10-01'
                     AND DATE '2026-10-03'
GROUP BY team_id
ORDER BY total_cpu_ms DESC;


-- 4. Daily resource consumption by team.

SELECT
    event_date,
    team_id,
    SUM(cpu_ms) AS cpu_ms,
    SUM(physical_input_bytes) AS input_bytes
FROM agg_daily_team_usage
GROUP BY event_date, team_id
ORDER BY event_date, team_id;


-- 5. Most frequently queried tables.

SELECT
    d.catalog_name,
    d.schema_name,
    d.table_name,
    SUM(a.query_count) AS total_queries
FROM agg_daily_table_usage a
JOIN dim_tables d
    ON a.table_id = d.table_id
GROUP BY
    d.catalog_name,
    d.schema_name,
    d.table_name
ORDER BY total_queries DESC;

