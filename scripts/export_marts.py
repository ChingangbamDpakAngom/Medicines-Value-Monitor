"""Export mart and dimension tables to Parquet for Power BI (Get Data > Parquet) or any other tool.

Usage: python scripts/export_marts.py
Output: data/export/<table>.parquet
"""
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get("DUCKDB_PATH") or ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "data" / "export"
TABLES = ["mart_icb_monthly", "mart_practice_monthly", "mart_branded_savings", "mart_low_value",
          "dim_icb", "dim_practice", "dim_bnf"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    for t in TABLES:
        path = OUT / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{path.as_posix()}' (FORMAT parquet)")
        rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"{t}: {rows:,} rows -> {path} ({path.stat().st_size / 1e6:,.1f} MB)")


if __name__ == "__main__":
    main()
