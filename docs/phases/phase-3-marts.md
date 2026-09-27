# Phase 3: Marts, the business logic

**Goal:** answer the project's two questions with tested tables the dashboard can read directly.
1. How much could be saved if branded drugs were prescribed generically?
2. How much is spent on items NHS England says should not routinely be prescribed?

**Code:** `dbt/models/intermediate/`, `dbt/models/marts/`, `dbt/seeds/brand_exceptions.csv`, `dbt/tests/`.

## Model lineage

```
stg_epd ──┬─> int_generic_unit_price ──┐
          │   brand_exceptions (seed) ─┼─> mart_branded_savings ──┐
          ├───────────────────────────-┘                          │
          │   low_value_medicines (seed) ──> mart_low_value ──────┼─> mart_icb_monthly
          ├─> dim_icb ────────────────────────────────────────────┘
          └─> dim_practice
```

| Model | Grain | What it does |
|---|---|---|
| `int_generic_unit_price` | month × generic presentation | Reference price per unit: each practice's own price (`sum(nic) / sum(total_quantity)`), then the **median** across practices |
| `mart_branded_savings` | month × practice × generic equivalent | Branded spend vs. the same quantity at the generic price. `saving = greatest(nic − total_quantity × price, 0)`. Excludes brand-exception drugs |
| `mart_low_value` | month × practice × category | Spend matching the low-value rules, minus exclusion rules |
| `dim_practice`, `dim_icb` | practice / ICB | Latest name, postcode and region (`arg_max(..., month)`) |
| `mart_icb_monthly` | month × ICB | Headline table: totals, savings, low-value spend, plus rates **per £1,000 of spend** |

## Results (May–July 2026)

| Month | Total NIC | Potential generic saving | Low-value spend |
|---|---|---|---|
| 2026-05 | £938.1M | £10.66M (1.14%) | £3.65M |
| 2026-06 | £997.3M | £10.84M (1.09%) | £3.78M |
| 2026-07 | £1,044.6M | £11.79M (1.13%) | £3.76M |

- **Top savings (July):** lamotrigine, dapagliflozin (generic launched, but the Forxiga brand is still prescribed), levetiracetam, the fluticasone/azelastine nasal spray, venlafaxine MR, micronised progesterone and melatonin MR. These are recognisable real-world examples, which is a good sign the logic is right.
- **Variation between ICBs:** Cornwall shows £18.20 of potential saving per £1,000 spent, against ~£11.30 nationally. A rate is needed to compare ICBs of different sizes fairly.

## Key decisions

**Reference price = median of practice-level prices**
- *Practice-level first:* rows are split by prescription size (phase 2 finding), so quantities and costs are summed per practice before dividing.
- *Median, not mean:* a few practices paying unusual prices (special orders, supply problems) would drag a mean around. The median is robust.
- *Alternative:* the official Drug Tariff price. It's more authoritative, but it's another dataset to ingest. Noted as a future upgrade.

**Saving floored at zero**
- If a brand is *cheaper* than the generic (it happens with "branded generics"), prescribing it is good, not negative savings. Without the floor, those rows would cancel out real waste elsewhere.

**Brand exceptions, tied to guidance**
- 22 rules, each citing a reason: inhalers (device technique; BTS/NICE), insulins (biologics; MHRA), MHRA category 1 antiepileptics, narrow-therapeutic-index drugs (ciclosporin, tacrolimus, lithium), modified-release products where brands aren't interchangeable, and pancreatin.
- **Pancreatin was added after reviewing the results.** It topped the savings list at £1.2M, but BNF guidance says its brands aren't interchangeable. **Looking at the output, not just whether the tests pass, caught a misleading headline.**
- Whole chemicals are excluded (e.g. all diltiazem, not only the MR forms). This is conservative: it can only *under*-state savings, never invent them.
- A deliberate caveat: lamotrigine and levetiracetam are MHRA *category 2*, where switching is left to clinical judgement. They stay in, but should be presented as "review", not "switch".

**Rates per £1,000 of spend**
- Raw savings favour big ICBs. Normalising by total spend makes areas comparable.
- Per-patient rates would be better still, but need practice list sizes (a separate NHS Digital dataset). That's in the backlog.

## Testing: 27 checks, ~1 minute

- **Grain uniqueness on every mart**, written as an expression, e.g. `unique` on `concat_ws('|', month, practice_code, generic_equiv_code)`. This avoids adding the dbt_utils package for one test.
- **Reconciliation** (`assert_icb_monthly_reconciles_to_staging`): total NIC per month in the headline table equals staging, to the penny. It proves no joins dropped or duplicated money.
- **Rule overlap** (`assert_low_value_rules_do_not_overlap`): no drug matches two inclusion rules, which would double-count it.
- Plus `not_null` and `unique` on dimension keys.

## Concepts to know

- **Intermediate vs mart models:** intermediate models are reusable building blocks that nobody queries directly (the reference price). Marts are business-facing tables at a defined grain.
- **Dimensional modelling:** facts (measures at a grain, e.g. savings per practice-month) and dimensions (descriptive attributes, e.g. practice name). `mart_icb_monthly` is a pre-aggregated fact table built for the dashboard.
- **Median vs mean** for reference values under outliers.
- **Reconciliation tests:** the most valuable test in any pipeline. Totals must match across layers.
- **Normalisation (rates):** compare entities of different sizes per unit of spend or per patient.
- **`arg_max(value, month)`:** "the value from the latest month". A clean way to build slowly-changing attributes into a dimension.

## Interview questions

**Q: How do you calculate the potential saving?**
1. For every generic drug, I work out a reference price per unit: each practice's own price, then the median across practices.
2. For branded prescribing of a drug whose generic equivalent exists, the saving is what was spent minus the same quantity at the reference price, floored at zero.
3. Drugs where guidance says to prescribe by brand are excluded first: inhalers, insulins, certain antiepileptics and modified-release products.

**Q: How do you know the numbers are right?**
- *Tests:* grain uniqueness and a to-the-penny reconciliation between layers.
- *Plausibility:* ~1.1% of spend is a sensible order of magnitude, and the top drugs are known real-world examples (dapagliflozin after generic launch, melatonin MR).
- *Review:* reading the top of the list caught pancreatin, which passed every test but was clinically wrong to include.

**Q: What are the limitations?**
- The reference price comes from practice prices, not the Drug Tariff.
- Brand exceptions are applied at chemical level, which is conservative.
- Category 2 antiepileptics are shown, but need clinical review before any switch.
- Rates are per £ of spend, not per patient.
- 2 of NHS England's 23 low-value categories are omitted.

**Q: Why an intermediate model for the price?**
It's a reusable concept (the dashboard or future marts may want unit prices) with its own grain and tests. Inlining it would hide logic inside a bigger query and make it harder to test on its own.

**Q: How would this scale to 5 years of data?**
- Make `stg_epd` or the marts `incremental` by month, so each run only processes new months.
- Partition by month; the Parquet layout already does this.
- DuckDB handles ~1bn rows on a laptop. Beyond that, the same dbt models run on a cloud warehouse by changing the adapter.
