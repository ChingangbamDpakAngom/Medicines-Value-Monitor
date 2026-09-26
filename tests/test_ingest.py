"""Run: python tests/test_ingest.py  — checks CSV→Parquet keeps codes as text and casts measures."""
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
from epd import to_parquet  # noqa: E402

CSV = """YEAR_MONTH,PRACTICE_CODE,BNF_PRESENTATION_CODE,SNOMED_CODE,QUANTITY,ITEMS,TOTAL_QUANTITY,ADQ_USAGE,NIC,ACTUAL_COST
2026-07,A81001,0410030A0AAAEAE,042009311000001105,22,1,22,293.33333,8.17,8.9568
2026-07,-,0212000B0AAABAB,000000000000000001,28,2,56,,1.5,1.62
"""


def test_to_parquet():
    with tempfile.TemporaryDirectory() as d:
        csv, out = Path(d, "epd.csv"), Path(d, "epd.parquet")
        csv.write_text(CSV)
        assert to_parquet(csv, out) == 2
        rows = duckdb.sql(f"SELECT * FROM '{out.as_posix()}' ORDER BY ITEMS").fetchall()
        types = {r[0]: r[1] for r in duckdb.sql(f"DESCRIBE SELECT * FROM '{out.as_posix()}'").fetchall()}
        assert rows[0][3] == "042009311000001105"  # leading zero kept: codes stay text
        assert types["NIC"] == "DOUBLE" and types["PRACTICE_CODE"] == "VARCHAR"
        assert rows[1][7] is None  # empty measure -> NULL, not a crash


if __name__ == "__main__":
    test_to_parquet()
    print("ok")
