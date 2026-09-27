# Phase 2: Staging, profiling and reference data

**Goal:**
- a clean, typed and tested `stg_epd` model over the raw Parquet
- enough profiling of the real data to know what one row *means* before building any business logic
- the reference list of low-value medicines, as a dbt seed

**Code:**
- `dbt/models/staging/_sources.yml`: points dbt at the raw Parquet
- `dbt/models/staging/stg_epd.sql`: the staging model
- `dbt/models/staging/_stg_epd.yml`: its tests
- `dbt/seeds/low_value_medicines.csv`: the low-value medicines list

## What was built

**The source.** dbt-duckdb lets a source point at files instead of a table:

```yaml
meta:
  external_location: "read_parquet('../data/raw/epd/*/epd.parquet', hive_partitioning=false)"
```

- The glob picks up every month automatically.
- It matches only finished `epd.parquet` files. The `.tmp` file of a month still being written is ignored, so dbt can run *while* ingest is running.
- `hive_partitioning=false` because the folder key `year_month` would clash with the data's own `YEAR_MONTH` column.

**`stg_epd` (a view).** One job only: make raw data pleasant and safe to use. No business logic.
- Columns renamed to snake_case (`BNF_PRESENTATION_CODE` → `bnf_code`).
- `YEAR_MONTH` text (`2026-07`) parsed to a real `date`.
- `QUANTITY` renamed to **`quantity_per_item`** (see finding 1 below).
- `is_drug`: a 15-character code in BNF chapters 01–19.
- `is_generic` and `generic_equiv_code` are derived from the BNF code structure, **for drugs only**; they're NULL otherwise.
- Tests: `not_null` on month, practice, BNF code, items and NIC.
- Build time: the whole project (seed + view + 5 tests) runs in ~10 s over 18.6M rows.

## Profiling findings (July 2026)

The full, re-runnable investigation is in [`notebooks/01_profiling.ipynb`](../../notebooks/01_profiling.ipynb). It uses DuckDB over all 3 months, with outputs saved so it reads on GitHub. It also proves `TOTAL_QUANTITY = ITEMS × QUANTITY` on all 54,976,318 rows, shows that the only duplicates left after adding quantity are pooled unidentified prescribing (63 groups), and covers the hive-partition gotcha.

**Why a notebook for profiling but not for cleaning:** exploration is iterative and visual, so a notebook suits it. Cleaning must be repeatable, tested and reusable, so it lives in dbt. The notebook is the *evidence*, and `stg_epd.sql` holds the *rules*.

This is where most of the value in this phase came from. Each finding changed the design.

| # | Finding | Evidence | Impact |
|---|---|---|---|
| 1 | **Rows are split by prescription size.** `QUANTITY` is *per item*, not total | One practice × drug had 2 rows: 2 items × 60 and 4 items × 30. 4.0M code combinations appear more than once | The unit price must be `nic / total_quantity`. Using `QUANTITY` would have inflated unit prices by the number of items. The grain includes quantity-per-item |
| 2 | **11-character BNF codes** on 1.93M rows | All are chapters 20–23 (appliances, stoma, dressings, incontinence), ~£150M/month | The drug code structure doesn't apply, so generic logic is NULL for these via `is_drug` |
| 3 | **Branded spend with a generic equivalent is large** | £330M of £410M branded drug NIC (80%) has an equivalent generic that is also prescribed. It's concentrated in ch. 06 (endocrine) and ch. 03 (respiratory) | Much of it is legitimate brand prescribing (inhalers, insulins, modified-release) or priced the same as the generic. Savings must use the **price difference**, and phase 3 needs a brand-exceptions list |
| 4 | Unidentified prescribing is tiny | 15,017 rows, £0.6M (0.06%) | Kept, and flagged `is_unidentified`, so ICB totals still reconcile |
| 5 | No negative costs; 411 rows with NIC = 0 | | No cleaning needed; zero-cost rows are valid |
| 6 | **Hive-partition gotcha:** reading `year_month=202607/` folders makes DuckDB silently replace `YEAR_MONTH` (`'2026-07'`) with the folder value (`202607`) | Notebook section 0 | Always read with `hive_partitioning=false` |

The totals for sanity checks: 9,284 practices, 37 ICBs, 21,422 presentations, 113.4M items, £1,044.6M NIC.

## The low-value medicines seed

NHS England publishes a list of items that "should not routinely be prescribed in primary care", but as drug *names*, not codes. To turn it into codes:

1. **Take codes from a trusted source instead of guessing.** OpenPrescribing (University of Oxford's Bennett Institute) publishes each category as a measure definition on GitHub, with BNF code filters. 16 categories came straight from there, including the rubefacient *exclusions*: topical NSAIDs and capsaicin are allowed.
2. **Fill the gaps from our own data.** Five categories are defined in OpenPrescribing through the NHS medicines dictionary (dm+d), which we don't have: fentanyl immediate-release, glucosamine, herbal, perindopril arginine, and tramadol+paracetamol. They were found by searching `chemical_name` in the July data.
3. **Use the code structure for future-proof rules.** Characters 14–15 of a BNF code identify the *generic equivalent form*. So `0407020A0%AW` (fentanyl 100 mcg sublingual tablet) matches the generic *and* every brand of it (Abstral, Fenhuma…), including brands launched later.
4. **Validate.** The fentanyl rules were checked to make sure they catch no patches or injections, which are the forms legitimately excluded. Result: 0 false matches.

**Result:** 86 rules covering 21 of the 23 categories, and **£3.96M of low-value prescribing in July 2026**. The biggest categories were lidocaine plasters (£1.3M), liothyronine (£0.8M) and fentanyl IR (£0.3M).
- Left out, and documented: bath/shower emollients (the rule is based on product names) and insulin pen needles (the rule is based on price).
- Aliskiren matches nothing; it's no longer prescribed.

Seed column types are pinned in `dbt_project.yml` so dbt can never misread a code.

## Decisions and why

- **Staging is a view, not a table.** It avoids storing a second 18.6M-row copy per month. DuckDB scans Parquet fast enough that the view costs little. If marts get slow, switch it to `incremental` by month.
- **Profile before modelling.** The unit-price bug from finding 1 would have produced plausible-looking but wrong savings. The only defence is to look at real rows before writing business logic.
- **A seed for reference data.** It's small, changes rarely and needs review by a person, so it belongs in git as a CSV where changes are visible in diffs, and dbt loads it like a table.
- **Tests are light at this layer.** `not_null` only; no `unique`, because the grain isn't unique by design (finding 1). Uniqueness tests belong on the marts, whose grain we control.

## Concepts to know

- **Staging layer conventions (dbt):** one staging model per source table; rename, cast and light derivation only; no joins and no aggregation.
- **Grain:** what one row represents. Always establish it by testing uniqueness on the real data, not by reading documentation.
- **BNF code anatomy:** chapter (2), section (2), paragraph (2), sub-paragraph (1), chemical (2), product (2: `AA` = generic), strength/form (2), generic equivalent (2).
- **NIC vs actual cost:** NIC (net ingredient cost) is the list price of the drug. Actual cost is what the NHS paid after discounts and fees. Cost comparisons use NIC because it's consistent across practices.
- **Data profiling:** row counts, distinct counts, null and negative checks, duplicate checks, distributions by category.
- **Notebook vs pipeline:** notebooks are for exploration and communication. Pipelines (dbt) are for anything that must run the same way every time.

## Interview questions

**Q: Tell me about a data-quality issue you found.**
The `QUANTITY` column looked like total quantity, but profiling showed rows were duplicated per practice and drug. Digging in showed the source splits prescriptions by pack size: one row for items of 60 tablets and another for items of 30. `QUANTITY` is per item. `TOTAL_QUANTITY` is the real volume. Using the wrong one would have multiplied unit prices by the number of items and produced believable but wrong savings figures. I renamed the column in staging to `quantity_per_item` so nobody downstream makes the same mistake.

**Q: How did you decide what counts as a low-value medicine?**
- I used NHS England's list, with codes from OpenPrescribing's peer-reviewed definitions rather than my own guesses.
- Where their definitions needed a dataset I don't have (dm+d), I mapped the categories using chemical names in the data itself.
- I used the BNF generic-equivalent suffix so each rule catches brands too, validated that it caught nothing it shouldn't (for example fentanyl patches), and documented the two categories I left out.

**Q: Why isn't there a uniqueness test on staging?**
Because the source grain isn't unique on the business keys. It includes quantity per item. A uniqueness test there would either fail or have to include a measure column in the key, which is meaningless. I put uniqueness tests on the marts, where I define the grain by aggregation.

**Q: What's the difference between staging and marts?**
- Staging mirrors the source one-to-one, cleaned: same grain, better names and types.
- Marts are business-facing: aggregated to a grain that answers a question (ICB × month savings), joined to reference data, and tested for uniqueness.
