# Meta DWH — Trino & Apache Iceberg Usage Analytics

A lightweight, idempotent Data Warehouse prototype built with **DuckDB** and **Python** to track and analyze query usage patterns, resource consumption, and table popularity across a Trino and Apache Iceberg lakehouse environment.

---

## 📌 Project Overview

This repository addresses two core analytical requirements:
1. **User reach by table:** Determining distinct users accessing specific Iceberg tables over customizable periods.
2. **Team resource consumption:** Measuring computational effort (`cpu_ms`, `physical_input_bytes`, `spilled_bytes`) by team over time.

For full architectural details and data modeling decisions, see:
* [Architecture & Ingestion Design](docs/architecture.md)
* [Data Model & Granularity Specifications](docs/data-model.md)

---

## 🏗️ Repository Structure

```text
├── data/
│   ├── sample_events.csv          # Sample Trino raw query event logs
│   └── user_team_membership.csv   # Historical SCD Type 2 user-team mapping
├── sql/
│   ├── 01_schema.sql              # DWH DDL (Dimensions, Facts, Bridge, Aggregates)
│   └── 02_analytical_queries.sql  # Example analytical queries
├── src/
│   ├── __init__.py
│   └── pipeline.py                # Main ETL and transformation logic (DuckDB)
├── tests/
│   └── test_pipeline.py           # Unit and idempotency integration tests
├── architecture.md                # Production lakehouse architecture documentation
├── data-model.md                  # Dimensional modeling documentation
├── main.py                        # Entrypoint script to execute the pipeline
├── requirements.txt               # Python dependencies
└── README.md                      # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
* Python 3.9+
* Recommended: Virtual environment (`venv` or `conda`)

### 2. Installation
Clone the repository and install the required dependencies:

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## ⚙️ Running the Pipeline

To execute the end-to-end ingestion and transformation pipeline:

```bash
python main.py
```

This will:
1. Initialize the schema from `sql/01_schema.sql`.
2. Ingest raw query events and historical user-team memberships.
3. Resolve point-in-time team associations (SCD Type 2).
4. Populate dimension, fact, and bridge tables.
5. Recalculate daily aggregate tables for affected dates.
6. Record execution metadata in `pipeline_runs`.

---

## 🧪 Running the Tests

To run the automated test suite and verify pipeline idempotency:

```bash
python -m unittest discover tests
```
*(Or `python -m unittest test_pipeline.py` if tests are located in the root directory)*

The test suite validates:
* Fact table query counts and bridge relationship counts.
* Distinct user calculations on multi-table queries.
* Daily team resource aggregation accuracy.
* **Pipeline Idempotency:** Consecutive runs with the same input do not generate duplicate records or skew aggregates.

---

## 📊 Analytical Queries

The SQL queries answering the project questions are located in `sql/02_analytical_queries.sql`. You can execute them against the generated `meta_dwh.duckdb` database using the DuckDB CLI or Python.
