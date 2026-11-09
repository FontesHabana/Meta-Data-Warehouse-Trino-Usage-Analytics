CREATE TABLE IF NOT EXISTS dim_teams (
    team_id VARCHAR PRIMARY KEY,
    team_name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_users (
    user_id VARCHAR PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS user_team_membership (
    user_id VARCHAR NOT NULL,
    team_id VARCHAR NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL,
    PRIMARY KEY (user_id, team_id, valid_from)
);

CREATE TABLE IF NOT EXISTS dim_tables (
    table_id VARCHAR PRIMARY KEY,
    catalog_name VARCHAR NOT NULL,
    schema_name VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_queries (
    query_id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    team_id VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    event_date DATE NOT NULL,
    state VARCHAR NOT NULL,
    duration_ms BIGINT,
    cpu_ms BIGINT,
    physical_input_bytes BIGINT,
    peak_memory_bytes BIGINT,
    spilled_bytes BIGINT
);

CREATE TABLE IF NOT EXISTS bridge_query_tables (
    query_id VARCHAR NOT NULL,
    table_id VARCHAR NOT NULL,
    PRIMARY KEY (query_id, table_id)
);

CREATE TABLE IF NOT EXISTS agg_daily_table_usage (
    event_date DATE NOT NULL,
    table_id VARCHAR NOT NULL,
    query_count BIGINT NOT NULL,
    distinct_user_count BIGINT NOT NULL,
    PRIMARY KEY (event_date, table_id)
);

CREATE TABLE IF NOT EXISTS agg_daily_team_usage (
    event_date DATE NOT NULL,
    team_id VARCHAR NOT NULL,
    query_count BIGINT NOT NULL,
    cpu_ms BIGINT NOT NULL,
    physical_input_bytes BIGINT NOT NULL,
    spilled_bytes BIGINT NOT NULL,
    PRIMARY KEY (event_date, team_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id BIGINT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status VARCHAR NOT NULL,
    processed_queries BIGINT NOT NULL
);
