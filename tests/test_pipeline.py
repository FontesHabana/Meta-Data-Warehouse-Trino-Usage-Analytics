import unittest

import duckdb

from src.pipeline import DB_PATH, run_pipeline


class TestMetaDWH(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        run_pipeline()

    def setUp(self):
        self.con = duckdb.connect(str(DB_PATH), read_only=True)

    def tearDown(self):
        self.con.close()

    def test_query_granularity(self):
        count = self.con.execute(
            "SELECT COUNT(*) FROM fact_queries"
        ).fetchone()[0]

        self.assertEqual(count, 8)

    def test_query_table_relationships(self):
        count = self.con.execute(
            "SELECT COUNT(*) FROM bridge_query_tables"
        ).fetchone()[0]

        self.assertEqual(count, 10)

    def test_distinct_users_for_orders(self):
        result = self.con.execute("""
            SELECT COUNT(DISTINCT f.user_id)
            FROM fact_queries f
            JOIN bridge_query_tables b
                ON f.query_id = b.query_id
            WHERE b.table_id = 'hive.sales.orders'
        """).fetchone()[0]

        self.assertEqual(result, 3)

    def test_team_resource_consumption(self):
        result = self.con.execute("""
                                  SELECT SUM(cpu_ms)
                                  FROM agg_daily_team_usage
                                  WHERE team_id = 'analytics'
                                  """).fetchone()[0]

        self.assertEqual(result, 8000)

    def test_unknown_team_dimension_exists(self):
        result = self.con.execute("""
            SELECT COUNT(*)
            FROM dim_teams
            WHERE team_id = 'unknown'
        """).fetchone()[0]

        self.assertEqual(result, 1)

    def test_pipeline_is_idempotent(self):
        # Close the read-only connection before running the pipeline.
        self.con.close()

        run_pipeline()

        # Reopen the database after pipeline execution.
        self.con = duckdb.connect(str(DB_PATH), read_only=True)

        count = self.con.execute(
            "SELECT COUNT(*) FROM fact_queries"
        ).fetchone()[0]

        self.assertEqual(count, 8)

if __name__ == "__main__":
    unittest.main()
