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


def download(url: str, dest: Path) -> None:
    """Stream to dest, resuming a partial .part file if one exists."""
    part = dest.with_suffix(".part")
    done = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        if r.status_code == 416:  # already fully downloaded
            part.rename(dest)
            return
        r.raise_for_status()
        mode = "ab" if r.status_code == 206 else "wb"
        with open(part, mode) as f:
            for chunk in r.iter_content(chunk_size=8 << 20):
                f.write(chunk)
    part.rename(dest)


def to_parquet(csv: Path, out: Path) -> int:
    """Read everything as text (no type guessing), cast measures to DOUBLE, write ZSTD Parquet. Returns row count."""
    casts = ", ".join(f"CAST({c} AS DOUBLE) AS {c}" for c in NUMERIC)
    tmp = out.with_suffix(".tmp")
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * REPLACE ({casts}) FROM read_csv(?, header=true, all_varchar=true)) "
        f"TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)",
        [str(csv)],
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
        csv = out.parent / "epd.csv"
        if not csv.exists():
            print(f"{ym}: downloading")
            download(months[ym], csv)
        print(f"{ym}: converting")
        rows = to_parquet(csv, out)
        csv.unlink()
        print(f"{ym}: {rows:,} rows -> {out}")


if __name__ == "__main__":
    main()
