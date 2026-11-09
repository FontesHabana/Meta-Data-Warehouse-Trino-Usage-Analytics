from pathlib import Path
from datetime import datetime, timezone

import duckdb


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "meta_dwh.duckdb"
EVENTS_PATH = ROOT / "data" / "sample_events.csv"
MEMBERSHIP_PATH = ROOT / "data" / "user_team_membership.csv"
SCHEMA_PATH = ROOT / "sql" / "01_schema.sql"


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))

    try:
        # 1. Create the warehouse schema.
        con.execute(SCHEMA_PATH.read_text())

        run_id = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        started = datetime.now(timezone.utc).replace(tzinfo=None)

        # 2. Read raw query events.
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE raw_events AS
            SELECT
                query_id,
                user_id,
                CAST(started_at AS TIMESTAMP) AS started_at,
                CAST(ended_at AS TIMESTAMP) AS ended_at,
                state,
                CAST(cpu_ms AS BIGINT) AS cpu_ms,
                CAST(physical_input_bytes AS BIGINT)
                    AS physical_input_bytes,
                CAST(peak_memory_bytes AS BIGINT) AS peak_memory_bytes,
                CAST(spilled_bytes AS BIGINT) AS spilled_bytes,
                accessed_tables
            FROM read_csv(
                '{EVENTS_PATH.as_posix()}',
                header = true,
                all_varchar = true
            )
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY query_id
                ORDER BY started_at DESC
            ) = 1
        """)

        # 3. Read historical user-team assignments.
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE raw_membership AS
            SELECT
                user_id,
                team_id,
                CAST(valid_from AS DATE) AS valid_from,
                CAST(valid_to AS DATE) AS valid_to
            FROM read_csv(
                '{MEMBERSHIP_PATH.as_posix()}',
                header = true,
                all_varchar = true
            )
        """)

        # 4. Refresh the membership history in this demo.
        # In production, this would be an incremental SCD Type 2 load.
        con.execute("DELETE FROM user_team_membership")
        con.execute("""
            INSERT INTO user_team_membership
            SELECT user_id, team_id, valid_from, valid_to
            FROM raw_membership
        """)

        # 5. Populate team and user dimensions.
        con.execute("""
            INSERT INTO dim_teams
            SELECT DISTINCT team_id, team_id
            FROM raw_membership
            WHERE team_id NOT IN (
                SELECT team_id FROM dim_teams
            )
        """)

        con.execute("""
            INSERT INTO dim_teams
            SELECT 'unknown', 'Unknown team'
            WHERE NOT EXISTS (
                SELECT 1 FROM dim_teams WHERE team_id = 'unknown'
            )
        """)

        con.execute("""
            INSERT INTO dim_users
            SELECT DISTINCT r.user_id
            FROM raw_events r
            WHERE NOT EXISTS (
                SELECT 1 FROM dim_users u
                WHERE u.user_id = r.user_id
            )
        """)

        # 6. Resolve the user's team at query execution time.
        # If multiple memberships overlap, choose the latest valid_from.
        con.execute("""
            CREATE OR REPLACE TEMP TABLE enriched_events AS
            SELECT
                r.*,
                COALESCE(m.team_id, 'unknown') AS team_id,
                DATE(r.started_at) AS event_date,
                DATE_DIFF(
                    'millisecond',
                    r.started_at,
                    r.ended_at
                ) AS duration_ms
            FROM raw_events r
            LEFT JOIN user_team_membership m
                ON r.user_id = m.user_id
                AND DATE(r.started_at) >= m.valid_from
                AND DATE(r.started_at) < m.valid_to
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY r.query_id
                ORDER BY m.valid_from DESC NULLS LAST
            ) = 1
        """)

        # 7. Extract the tables referenced by each query.
        con.execute("""
            CREATE OR REPLACE TEMP TABLE staged_query_tables AS
            SELECT DISTINCT
                e.query_id,
                TRIM(t.table_ref) AS table_id,
                SPLIT_PART(TRIM(t.table_ref), '.', 1) AS catalog_name,
                SPLIT_PART(TRIM(t.table_ref), '.', 2) AS schema_name,
                SPLIT_PART(TRIM(t.table_ref), '.', 3) AS table_name
            FROM raw_events e,
            UNNEST(STRING_SPLIT(e.accessed_tables, '|'))
                AS t(table_ref)
            WHERE TRIM(t.table_ref) <> ''
              AND ARRAY_LENGTH(
                    STRING_SPLIT(TRIM(t.table_ref), '.')
                  ) = 3
        """)

        # 8. Populate the table dimension.
        con.execute("""
                    INSERT INTO dim_tables (table_id,
                                            catalog_name,
                                            schema_name,
                                            table_name)
                    SELECT DISTINCT s.table_id,
                                    s.catalog_name,
                                    s.schema_name,
                                    s.table_name
                    FROM staged_query_tables s
                    WHERE NOT EXISTS (SELECT 1
                                      FROM dim_tables d
                                      WHERE d.table_id = s.table_id)
                    """)

        # 9. Idempotent replacement of incoming queries.
        # Reprocessing the same query does not create duplicates.
        con.execute("""
            CREATE OR REPLACE TEMP TABLE affected_dates AS
            SELECT DISTINCT event_date
            FROM enriched_events
        """)

        con.execute("""
            DELETE FROM bridge_query_tables
            WHERE query_id IN (
                SELECT query_id FROM enriched_events
            )
        """)

        con.execute("""
            DELETE FROM fact_queries
            WHERE query_id IN (
                SELECT query_id FROM enriched_events
            )
        """)

        # One row per query.
        con.execute("""
            INSERT INTO fact_queries
            SELECT
                query_id,
                user_id,
                team_id,
                started_at,
                event_date,
                state,
                duration_ms,
                COALESCE(cpu_ms, 0),
                COALESCE(physical_input_bytes, 0),
                COALESCE(peak_memory_bytes, 0),
                COALESCE(spilled_bytes, 0)
            FROM enriched_events
        """)

        # One row per query-table relationship.
        con.execute("""
            INSERT INTO bridge_query_tables
            SELECT query_id, table_id
            FROM staged_query_tables
        """)

        # 10. Recalculate aggregates for affected dates only.
        # This supports repeatable processing and historical backfills.
        con.execute("""
            DELETE FROM agg_daily_table_usage
            WHERE event_date IN (
                SELECT event_date FROM affected_dates
            )
        """)

        con.execute("""
            INSERT INTO agg_daily_table_usage
            SELECT
                f.event_date,
                b.table_id,
                COUNT(DISTINCT f.query_id) AS query_count,
                COUNT(DISTINCT f.user_id) AS distinct_user_count
            FROM fact_queries f
            JOIN bridge_query_tables b
                ON f.query_id = b.query_id
            WHERE f.event_date IN (
                SELECT event_date FROM affected_dates
            )
            GROUP BY f.event_date, b.table_id
        """)

        con.execute("""
            DELETE FROM agg_daily_team_usage
            WHERE event_date IN (
                SELECT event_date FROM affected_dates
            )
        """)

        con.execute("""
            INSERT INTO agg_daily_team_usage
            SELECT
                event_date,
                team_id,
                COUNT(*) AS query_count,
                SUM(cpu_ms) AS cpu_ms,
                SUM(physical_input_bytes) AS physical_input_bytes,
                SUM(spilled_bytes) AS spilled_bytes
            FROM fact_queries
            WHERE event_date IN (
                SELECT event_date FROM affected_dates
            )
            GROUP BY event_date, team_id
        """)

        # 11. Record the pipeline execution.
        processed = con.execute(
            "SELECT COUNT(*) FROM enriched_events"
        ).fetchone()[0]

        finished = datetime.now(timezone.utc).replace(tzinfo=None)

        con.execute("""
            INSERT INTO pipeline_runs
            VALUES (?, ?, ?, ?, ?)
        """, [
            run_id,
            started,
            finished,
            "SUCCESS",
            processed
        ])

        print(f"Pipeline completed successfully: {processed} queries processed.")
        print(f"Warehouse: {DB_PATH}")

    except Exception:
        raise
    finally:
        con.close()


if __name__ == "__main__":
    run_pipeline()
