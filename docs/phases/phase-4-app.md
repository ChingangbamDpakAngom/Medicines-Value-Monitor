# Phase 4: Dashboard (Streamlit)

**Goal:** a dashboard someone without SQL can use to answer "where is the money, and in which drugs?", nationally or for one ICB.

**Code:** `app/streamlit_app.py` (one file, ~200 lines). The smoke test is `tests/test_app.py`. It also needed two small dbt models: `dim_bnf` (drug names) and `mart_practice_monthly` (practice drill-down).

```bash
cd dbt && ../.venv/Scripts/dbt build && cd ..
.venv/Scripts/streamlit run app/streamlit_app.py
```

## What it shows

| Area | Content |
|---|---|
| Sidebar filters | Month (latest by default) and ICB ("All England" or one ICB) |
| KPI tiles | Total spend, potential generic saving (with % of spend), low-value spend (with £ per £1k) |
| **Where** | All England: the 37 ICBs ranked by saving per £1,000 spent. One ICB: its top 25 practices, with a minimum-spend slider |
| **Which drugs** | Top 15 drugs by potential saving. Antiepileptics labelled "(review)" |
| **Low-value items** | Spend by NHS England category |
| **Trend** | Saving per £1k and low-value spend per £1k by month, as two separate charts |
| **Method** | Plain-English definitions and limitations |

Every chart has a "Table view" expander with the underlying numbers.

## Architecture decisions

**The app reads marts only, read-only**
- All business logic lives in dbt, where it's tested. The app only filters and draws. If a number is wrong, there's exactly one place to fix it.
- `duckdb.connect(..., read_only=True)` means the dashboard can never corrupt the warehouse, and several app sessions can read at once.

**Two new dbt models instead of computing in the app**
- `mart_practice_monthly`: practice totals are needed for fair "per £1k" ranking. Computing them in the app would mean scanning 55M rows on every click. As a mart they're pre-aggregated and tested.
- `dim_bnf`: drug names for chart labels. The staging view can't be queried from the app anyway, because its Parquet path is relative to `dbt/`, which is a deliberate boundary.

**Caching**
- `@st.cache_resource` holds one DB connection per server. `@st.cache_data` stores query results keyed by SQL and parameters, so switching back to a filter already viewed is instant.

**Parameterised SQL** (`where month = ? and icb_code = ?`)
- Filter values are never pasted into SQL strings. That's correct practice against SQL injection, and it gives the cache clean keys.

## Chart design decisions (and why)

These come from a data-visualisation checklist, and each is a common mistake avoided:
- **Horizontal bars for rankings:** long names (ICBs, drugs) stay readable. Sorted by value, so the chart *is* the ranking.
- **Rates, not raw £, for ranking areas:** raw savings just rank ICBs by size. Per £1,000 of spend compares like with like.
- **Two charts, never a dual y-axis:** saving and low-value spend have different scales. Two y-axes on one chart invite false comparisons.
- **One colour per measure, used consistently:** blue always means savings and orange always means low-value, on every tab. Each chart is a single series, so no legend is needed; the title names it.
- **Zero-based y-axis on trends:** otherwise a ±3% wobble looks like a crash.
- **Table view on every chart:** accessibility for screen-reader users, and a fallback for anyone who wants exact numbers.

**Found by looking at the rendered app, not by tests:**
- Every other ICB label was hidden because rows were too tight. Fixed with more row height and `labelOverlap=False`.
- "NHS … INTEGRATED CARE BOARD" repeated on all 37 names, eating label space. It's stripped in one SQL expression, shared by the dropdown and the chart.
- The KPI badges showed a green "↑" arrow, which reads as "went up". But they're ratios, not changes, so the arrow was removed.
- The antiepileptic "needs review" flag was only in the table, yet lamotrigine *tops* the chart. The flag was moved into the chart label.

## Testing

`tests/test_app.py` uses Streamlit's built-in `AppTest` to run the script headlessly. It asserts that the app renders nationally without exceptions, that the saving KPI is present, and that picking an ICB switches to the practice drill-down (the slider appears). It's the cheapest check that catches a broken query or a renamed column after a dbt change.

## Concepts to know

- **Separation of concerns:** transformation (dbt) vs presentation (app). The app has no business logic.
- **Caching layers:** resource cache (connections) vs data cache (results). Why caching matters in Streamlit's rerun-the-whole-script model.
- **Streamlit's execution model:** every widget interaction reruns the script top to bottom. Caching is what makes this fast.
- **Chart choice:** bars for comparing categories, lines for change over time, a single number (KPI tile) for a headline. Avoid dual axes, pie charts with many slices, and colour as the only carrier of meaning.
- **Normalisation for fair comparison:** per £ spend here, per patient in the future.

## Interview questions

**Q: Why Streamlit rather than Power BI or Tableau?**
- Streamlit keeps the whole project in Python and git: reviewable, testable, free and deployable anywhere.
- Power BI is better for self-service slicing by business users. The marts are BI-ready, so connecting Power BI later is an export, not a rebuild (phase 5).

**Q: How do you keep the dashboard fast on 55M rows?**
- It never touches 55M rows. dbt pre-aggregates to marts: ICB × month is ~110 rows, and practice × month ~28k.
- The app only filters those, and results are cached per filter combination.

**Q: How would you deploy it?**
- Streamlit Community Cloud or a container. Mart tables would be exported to Parquet (or the DuckDB file shipped), because the raw data is too big to deploy.
- In production it would read from a warehouse, with a scheduled dbt run refreshing the marts monthly.

**Q: What would you add next?**
- Per-patient rates (practice list sizes).
- Practice benchmarking against peers with similar list sizes.
- A downloadable CSV per view.
- "Top savings drugs" for each practice on click.
