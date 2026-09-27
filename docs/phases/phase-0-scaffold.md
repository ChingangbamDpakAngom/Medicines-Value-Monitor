# Phase 0: Scaffold

**Goal:** a reproducible environment where `dbt debug` passes, before any data work.

## What was built

| File | Purpose |
|---|---|
| `requirements.txt` | Exact pinned versions: duckdb 1.5.5, dbt-core 1.12.5, dbt-duckdb 1.11.0, pandas 3.0.6, streamlit 1.64.0, requests 2.34.2 |
| `.python-version` | `3.12`, which tells `uv` which interpreter to use |
| `dbt/dbt_project.yml` | Project config. Staging models build as **views**; intermediate and marts build as **tables** |
| `dbt/profiles.yml` | Connection: a DuckDB file at `data/warehouse.duckdb` |
| `.gitignore` | Ignores `data/`, `.venv/`, and dbt's `target/` and `logs/` |
| `data/.gitkeep` | Keeps the empty `data/` folder in git, because DuckDB won't create the parent folder of its database file |

## Decisions and why

**DuckDB instead of Postgres, Snowflake or Spark**
- The data is ~18M rows per month, and a few months is ~50M rows. That's "medium data": too big for comfortable pandas, but far too small to justify a cluster.
- DuckDB is an in-process, columnar analytical database. There's no server to run, it reads Parquet and CSV natively (including over HTTP), and it uses all CPU cores.
- It costs nothing and runs on a laptop, which suits a portfolio project anyone can clone and run.

**dbt for transformations**
- SQL models are version-controlled and dependency-ordered through `ref()`/`source()`, with tests (`not_null`, `unique`, custom) and auto-generated lineage docs.
- It's the industry standard for the "T" in ELT. Using it shows analytics-engineering practice, not just scripting.

**ELT, not ETL**
- Raw data is landed almost untouched as Parquet (Extract + Load). All business logic lives in dbt (Transform).
- If the logic changes, you re-run dbt; you don't re-download 23 GB.

**Views for staging, tables for marts**
- Staging is a thin rename/cast layer over ~50M rows. A view avoids storing a second copy.
- Marts are small, aggregated and queried repeatedly by the app, so they're materialised as tables for speed.

**Python 3.12, not the system 3.14**
- dbt-core supports Python versions a step behind the newest. Pinning 3.12 through `uv` avoids install and runtime failures.
- `uv` is a fast Rust-based replacement for pip/venv. It downloads the pinned Python automatically.

**Pinned versions**
- `pip install dbt-duckdb` gives a different version next month. Pinning exact versions makes the project reproducible for a reviewer, or for CI later.

**`profiles.yml` inside the repo**
- dbt normally reads `~/.dbt/profiles.yml`, which is outside the project. Keeping it in `dbt/` means clone-and-run works.
- It holds no secrets (it's a local file path), so committing it is safe. With a cloud warehouse, credentials would come from environment variables instead.

**Git workflow**
- One branch per phase (`phase-0-scaffold`), fast-forward merged into `main`. Commits are small and focused (docs separate from code).

## Concepts to know

- **OLTP vs OLAP:** row stores (Postgres) are optimised for many small transactions. Column stores (DuckDB, Snowflake, BigQuery) are optimised for scanning a few columns across many rows. Analytics workloads are OLAP.
- **dbt materialisations:** `view`, `table`, `incremental` (only process new data, e.g. new months), `ephemeral` (inlined as a CTE).
- **dbt `source` vs `ref`:** `source()` points to raw data dbt doesn't own. `ref()` points to another dbt model and builds the dependency graph (DAG).

## Interview questions

**Q: Why DuckDB rather than a cloud warehouse?**
The data fits on one machine: ~1 GB compressed per month. DuckDB gives warehouse-style SQL performance with no infrastructure or cost, and anyone can reproduce the project. The dbt models are portable; switching to Snowflake or BigQuery means changing the adapter in `profiles.yml`, and most SQL carries over.

**Q: What would change in production?**
- Raw Parquet would go to object storage (S3 or Azure Blob) instead of local disk.
- dbt would run on a schedule (GitHub Actions, Airflow or Dagster), with credentials held in a secrets manager.
- CI would run `dbt build` on every pull request.

**Q: Why ELT instead of ETL?**
Loading raw data first keeps an immutable copy of the source. Transformations become cheap to change and re-run, and they're testable SQL rather than logic hidden inside the ingestion code.
