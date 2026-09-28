# Phase 5: CI, Power BI export and the README

**Goal:** make the project trustworthy and easy to evaluate for someone who will never download 23 GB:
- CI that proves the whole pipeline works on every push
- a way to get the data into Power BI
- a README that tells the story in 30 seconds

## 1. Configuration through environment variables

CI must build against a small sample, not `data/raw`, and must never overwrite a real warehouse. Two settings became environment variables, **with the old values as defaults**, so local behaviour is unchanged:

| Variable | Used in | Default |
|---|---|---|
| `EPD_GLOB` | `dbt/models/staging/_sources.yml` (via `env_var()`) | `../data/raw/epd/*/epd.parquet` |
| `DUCKDB_PATH` | `dbt/profiles.yml`, the app, the export script | `../data/warehouse.duckdb` |

This is the **twelve-factor app** idea: config lives in the environment, code stays the same everywhere.

## 2. The CI fixture: a real sample, not synthetic data

`tests/fixtures/epd/` holds the **complete** rows for 4 real practices (the largest and a mid-sized practice in each of the 2 largest ICBs) plus a slice of unidentified prescribing, for all 3 months. That's 77k rows and 1.6 MB, committed to git.

**Why real rows rather than invented ones:**
- They carry the real quirks: rows split by prescription size, 11-character appliance codes, branded/generic pairs and unidentified rows. Synthetic data only contains the cases you already thought of.
- They exercise the business logic: the fixture produces 3,715 savings rows and hits 12 low-value categories, so the tests aren't passing vacuously on empty tables.
- The data is published under the Open Government Licence, so committing a sample is allowed.

**Why whole practices rather than random rows:** a random sample would break the practice-level logic (reference prices and practice totals). Sampling by *entity* keeps each practice's data internally consistent.

## 3. GitHub Actions (`.github/workflows/ci.yml`)

On every push to `main` and every pull request, it:
1. Sets up Python 3.12 (with a pip cache) and installs the pinned `requirements.txt`.
2. Runs the ingest unit test.
3. Runs `dbt build` on the fixture: all models, seeds and tests, including uniqueness, the reconciliation and the rule-overlap checks.
4. Runs the dashboard smoke test (`AppTest`) against the freshly built warehouse.

It was simulated locally before pushing, with the same environment variables and a throwaway database: 32/32 dbt checks and the app test passed.

## 4. Power BI export

`scripts/export_marts.py` writes the 7 mart and dimension tables to `data/export/*.parquet` (~77 MB, mostly the practice × drug savings detail).

To use them in Power BI Desktop:
1. **Get Data → Parquet**, and load each file.
2. In model view, relate `icb_code` from `dim_icb` to the marts, and `practice_code` from `dim_practice` to the practice-level marts. That makes a star schema.
3. Build visuals on the `saving_per_1000_nic` and `low_value_per_1000_nic` rates, not raw £, for fair comparison.

The same files work in Tableau, Excel (Power Query) or pandas. Parquet keeps the types, so dates stay dates and codes stay text.

No `.pbix` file is committed. It's a binary that can't be reviewed in git, and Power BI isn't available in this environment. The export is the reproducible part.

## 5. README as the front page

Recruiters and interviewers give a repo about 30 seconds, so the README puts things in this order:
1. the question
2. the headline findings in a table
3. a screenshot
4. how it works
5. how to run it
6. limitations

The CI badge shows the pipeline is live, and each layer links to its phase doc for depth.

## The first CI run failed, and how it was debugged

The first push went red at **`pip install`**, before any project code ran. The job logs need a GitHub login, so the failure was reproduced locally instead, one hypothesis at a time:

1. **Are the versions compatible?** `uv pip compile --python-platform linux` resolved cleanly. The pins were fine.
2. **Does pip (not uv) resolve them?** A native `pip install --dry-run` succeeded, so pip's resolver was fine too.
3. **Does every package have a Linux wheel?** `pip download --platform manylinux… --only-binary=:all:` for each dependency: all had one.
4. **What else runs at install time on Linux?** `dbt-core 1.12` added a dependency, `dbt-core-experimental-parser`, published only as a *source* package. Its build step **downloads a platform binary from a GitHub release during `pip install`**. It was the one Linux-only moving part in the install.

**Fix: pin `dbt-core==1.11.9`**, the last version without that dependency. The project uses nothing from 1.12. After the pin, a strict wheels-only resolve for Linux/Python 3.12 passes, meaning nothing is built or downloaded outside PyPI. Both the fixture build and the full 55M-row build were re-run: 32/32.

Lessons:
- **Reproduce CI locally when logs aren't available.** Simulate the target platform (`--platform`, `--python-version`) and remove hypotheses one at a time.
- **Newest isn't always best for a pipeline dependency.** Prefer versions whose install is plain wheels. Fewer moving parts means fewer ways for CI to break, and less supply-chain surface: a build step that fetches binaries at install time bypasses the package index.
- **Pinning exact versions** (phase 0) made this debuggable: the failure was deterministic, not "something changed upstream".

Also bumped: `actions/checkout@v5` and `actions/setup-python@v6`, because GitHub deprecated Node 20 for the older versions.

## A correction found in this phase

While exporting, `dim_icb` showed 37 rows, but one is the unidentified `-` code: **there are 36 ICBs**. The docs had said "37 ICBs" in four places, because `count(distinct icb_code)` silently included the placeholder. All four were corrected.
- **Lesson:** check what a distinct count includes before quoting it. Placeholder codes ('-', 'UNKNOWN', 0) inflate counts.

## Concepts to know

- **CI (continuous integration):** automatically build and test every change, so breakage is caught at the commit that caused it.
- **Test fixtures:** small, representative, versioned datasets that make tests fast and deterministic.
- **Twelve-factor config:** environment variables instead of hard-coded paths.
- **Star schema:** fact tables (marts) joined to dimension tables (ICB, practice, drug) on keys. This is the shape BI tools expect.
- **Sampling by entity vs by row:** keeps aggregates within an entity valid.

## Interview questions

**Q: Tell me about a CI failure you debugged.**
- The first run failed at `pip install`, and I couldn't read the logs.
- I reproduced it locally by simulating Linux + Python 3.12 with pip's platform flags, and ruled out hypotheses in order: version conflicts, then the pip resolver, then missing Linux wheels.
- What was left was a new transitive dependency of dbt-core 1.12 that downloads a binary from GitHub during installation. I pinned dbt-core 1.11.9, verified that a strict wheels-only install works, and re-ran the full build.

**Q: How do you test a pipeline whose real input is 23 GB?**
- With a committed fixture: complete rows for 4 real practices across 3 months, 1.6 MB.
- CI builds every model and runs every dbt test on it, then renders the dashboard. The real quirks are in there because it's real data, and I check the fixture actually produces savings and low-value rows, so tests can't pass on empty tables.

**Q: How would someone use this in Power BI?**
- Run the export script, then Get Data → Parquet and relate the dimensions to the marts.
- All the logic is already computed and tested in dbt, so Power BI only visualises. The numbers can't drift between the dashboard and the report.

**Q: What's the difference between your CI and a production pipeline?**
- CI checks the code is correct on a sample. Production would also run on a schedule against the full new month, with alerting.
- It would also add data-quality checks on the new data itself: row counts vs the portal, and month-over-month change thresholds.

**Q: If you had another month, what would you add?**
- Per-patient rates (NHS Digital practice list sizes).
- Drug Tariff reference prices.
- Incremental dbt models so each month adds instead of rebuilding.
- The two missing low-value categories.
- A deployed dashboard (Streamlit Community Cloud) reading the exported marts.
