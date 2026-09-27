# Phase 1: Ingest

**Goal:** land the most recent N months of the English Prescribing Dataset (EPD) as local Parquet, one file per month. Re-running must be safe.

**Code:** [`ingest/epd.py`](../../ingest/epd.py), with its test in [`tests/test_ingest.py`](../../tests/test_ingest.py).

```bash
python ingest/epd.py --months 3
```

## How it works

1. **Discover:** call the NHSBSA Open Data Portal's CKAN API (`package_show`). It lists every monthly file (resource) in the dataset. Names like `EPD_SNOMED_202607` are matched with a regex to get `{YYYYMM: url}`.
2. **Pick:** sort the months and take the last N.
3. **Skip:** if `data/raw/epd/year_month=YYYYMM/epd.parquet` already exists, skip that month. Re-runs are no-ops.
4. **Stream → Parquet:** one DuckDB `COPY` statement reads the CSV straight from the URL and writes compressed Parquet. The CSV never touches the disk.
5. **Atomic write:** DuckDB writes to `epd.tmp`, counts the rows, then renames it to `epd.parquet`. A crash never leaves a half-written file that step 3 would mistake for a finished month.

```sql
COPY (
  SELECT * EXCLUDE (ADDRESS_1, ADDRESS_2, ADDRESS_3, ADDRESS_4)
           REPLACE (CAST(NIC AS DOUBLE) AS NIC, ...)
  FROM read_csv(<url>, header=true, all_varchar=true)
) TO 'epd.tmp' (FORMAT parquet, COMPRESSION zstd)
```

## What we found about the source

- Two datasets exist. The original `english-prescribing-data-epd` **stops at 2025-06**. The current one is `english-prescribing-dataset-epd-with-snomed-code` (2020-11 onwards).
  - Lesson: check the source's freshness before building on it; don't assume.
- Each month is ~18.6M rows and ~7.7 GB of CSV.
- There are 27 columns: geography (region → ICB → PCO → practice), BNF drug codes and names, `SNOMED_CODE`, and the measures `ITEMS`, `QUANTITY`, `TOTAL_QUANTITY`, `ADQ_USAGE`, `NIC`, `ACTUAL_COST`.
- `YEAR_MONTH` is text like `2026-07`. Unidentified prescribing (no practice) has `PRACTICE_CODE = '-'`.

## Decisions and trade-offs

**Iteration 1 → 2: download-then-convert → streaming.** This is the most interesting story in this phase.
- **v1** downloaded each CSV to disk (with resumable HTTP `Range` requests), converted it, then deleted it. Peak disk use was ~9 GB per month.
- The laptop had ~27 GB free, which was tight for 3 months plus everything else.
- **v2** lets DuckDB read the CSV over HTTP and write Parquet directly. The only disk used is the output: 315 MB for July 2026.
- **What we gave up:** resume within a month. If the connection drops, that month restarts from zero. Finished months are still skipped, so the cost is at most one month's re-download. That's an acceptable trade for a monthly batch job.

**`all_varchar=true`, then cast only the measures**
- CSV readers guess column types from a sample, and codes are identifiers, not numbers. `SNOMED_CODE` or a code with a leading zero would be corrupted if parsed as an integer.
- Letting a sample decide the type is also fragile: row 5,000,000 can break the guess.
- Reading everything as text and explicitly casting the six measures to `DOUBLE` is deterministic.

**Parquet + ZSTD instead of keeping the CSV**
- **Columnar:** queries read only the columns they need.
- **Compressed:** 25× smaller than the CSV here (7.8 GB → 315 MB). Repetitive text columns such as practice and ICB names compress extremely well.
- **Typed:** it stores its own schema.
- **Fast filtering:** it keeps min/max statistics per row group, so a query can skip chunks that can't match its filter (predicate pushdown).

**Dropped `ADDRESS_1`–`ADDRESS_4`**
- Four wide text columns repeated on 18M rows, and nothing uses them; the postcode is kept. This is the only transformation done at ingest. Everything else waits for dbt, keeping to ELT.

**Hive-style folders (`year_month=YYYYMM/`)**
- One folder per month makes "which months do I have?" a directory listing. It also lets query engines prune by month.
- In staging we read with `hive_partitioning=false`, because the data already has a `YEAR_MONTH` column and the folder key would collide with it.

**Discover URLs through the API, never hard-code them**
- New months appear automatically, and URL changes don't break the script.

**No pandas here**
- 18.6M rows × 27 columns would need several GB of RAM in pandas. DuckDB streams it with bounded memory.
- pandas is used later, on the small aggregated marts.

## Testing

`tests/test_ingest.py` runs `to_parquet` on a two-row synthetic CSV and asserts:
- codes keep their leading zeros (they stay text)
- the measures come out as `DOUBLE`
- an empty measure becomes `NULL` instead of crashing
- the address columns are dropped

The live API discovery was checked manually: 69 months were found (2020-11 → 2026-07).

## Numbers from the real run

| Month | Rows | Parquet size | Time |
|---|---|---|---|
| 2026-05 | 18,000,093 | 303 MB | ~28 min |
| 2026-06 | 18,374,449 | 311 MB | ~27 min |
| 2026-07 | 18,601,776 (matches the portal's own count exactly) | 315 MB (vs 7.8 GB CSV, **25× smaller**) | ~28 min |
| **Total** | **54,976,318** | **929 MB** | |

July 2026 totals: 9,284 practices, 37 ICBs, 21,422 distinct presentations, 113.4M items, £1,044.6M NIC (£1,000.6M actual cost).

## Concepts to know

- **Idempotency:** running the job twice gives the same result as running it once. Here it comes from skip-if-exists plus atomic rename.
- **Atomic write (write-temp-then-rename):** a rename is atomic on the same filesystem, so readers see either no file or a complete file.
- **Streaming vs batch download:** memory and disk stay bounded, but you lose resumability.
- **CKAN:** an open-source data-portal platform, also used by data.gov.uk. Its `package_show` endpoint returns a dataset's metadata and file list.
- **Row groups and predicate pushdown in Parquet.**

## Interview questions

**Q: Walk me through your ingestion.**
- The script calls the portal's API to list the monthly files and picks the latest N.
- For each month it streams the CSV straight into Parquet with DuckDB, writing to a temp file and renaming it once finished.
- It's idempotent (finished months are skipped), types are explicit, and nothing lands on disk except the compressed output.

**Q: You changed the design mid-phase. Why?**
The first version downloaded the full 7.7 GB CSV before converting, needing ~9 GB of scratch space per month, which was tight on my laptop. I switched to streaming, cutting disk use to the 315 MB Parquet output. The cost was losing resume-within-a-month. That's fine for a monthly batch where a retry costs at most one month.

**Q: How would you make this production-grade?**
- Write to object storage (S3 or ADLS) instead of local disk.
- Run it on a schedule with retries and alerting.
- Record ingested months and row counts in a small audit table, and compare them with the portal's published row counts.
- Add a schema check that fails loudly if the column list changes.

**Q: How would you handle the source schema changing?**
- Detect it: compare the header to an expected column list and fail fast.
- Absorb it: keep ingest dumb (text in, Parquet out) and map old names to new ones in the dbt staging layer. An example is `STP_*` → `ICB_*` for pre-2022 months.

**Q: Why not load straight into the DuckDB database?**
- Parquet files are immutable, per-month and engine-agnostic. The same files work in Spark, Polars, pandas or Power BI.
- The warehouse becomes disposable: delete `warehouse.duckdb` and `dbt build` rebuilds it from the raw files.
