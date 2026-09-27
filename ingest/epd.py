"""Download monthly EPD (SNOMED) CSVs from the NHSBSA Open Data Portal and convert each to Parquet.

Usage: python ingest/epd.py --months 3
Output: data/raw/epd/year_month=YYYYMM/epd.parquet (existing months are skipped).
"""
import argparse
import re
from pathlib import Path

import duckdb
import requests

DATASET = "english-prescribing-dataset-epd-with-snomed-code"
API = "https://opendata.nhsbsa.net/api/3/action/package_show"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "epd"
NUMERIC = ["QUANTITY", "ITEMS", "TOTAL_QUANTITY", "ADQ_USAGE", "NIC", "ACTUAL_COST"]


def list_months() -> dict[str, str]:
    """{'YYYYMM': csv_url} for every monthly resource in the dataset."""
    resources = requests.get(API, params={"id": DATASET}, timeout=60).json()["result"]["resources"]
    months = {}
    for r in resources:
        m = re.fullmatch(r"EPD_SNOMED_(\d{6})", r["name"])
        if m:
            months[m[1]] = r["url"]
    return months


def to_parquet(src: str, out: Path) -> int:
    """Stream a CSV (local path or URL, never saved to disk) to ZSTD Parquet. Returns row count.

    Everything is read as text (no type guessing); only measures are cast to DOUBLE. Address lines are dropped.
    """
    casts = ", ".join(f"CAST({c} AS DOUBLE) AS {c}" for c in NUMERIC)
    tmp = out.with_suffix(".tmp")
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * EXCLUDE (ADDRESS_1, ADDRESS_2, ADDRESS_3, ADDRESS_4) REPLACE ({casts}) "
        f"FROM read_csv(?, header=true, all_varchar=true)) "
        f"TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)",
        [src],
    )
    rows = con.execute("SELECT count(*) FROM read_parquet(?)", [tmp.as_posix()]).fetchone()[0]
    tmp.rename(out)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=3, help="number of most recent months to fetch")
    args = ap.parse_args()

    months = list_months()
    for ym in sorted(months)[-args.months:]:
        out = RAW / f"year_month={ym}" / "epd.parquet"
        if out.exists():
            print(f"{ym}: exists, skipping")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"{ym}: streaming {months[ym]}")
        rows = to_parquet(months[ym], out)
        print(f"{ym}: {rows:,} rows -> {out} ({out.stat().st_size / 1e6:,.0f} MB)")


if __name__ == "__main__":
    main()
