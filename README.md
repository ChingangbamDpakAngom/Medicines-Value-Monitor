# NHS Prescribing Analysis

Analysis of NHSBSA English prescribing data: DuckDB + dbt → pandas → Power BI / Streamlit.

Status: in progress.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design and plan.

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
cd dbt && ../.venv/Scripts/dbt debug
```

## Run

```bash
.venv/Scripts/python ingest/epd.py --months 3      # ~30 min per month, ~310 MB Parquet each
cd dbt && ../.venv/Scripts/dbt build && cd ..      # 29 models/tests, ~1 min
.venv/Scripts/streamlit run app/streamlit_app.py   # dashboard at http://localhost:8501
```
