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
