"""Medicines Value Monitor: generic-prescribing savings and low-value prescribing in English primary care.

Run: streamlit run app/streamlit_app.py   (after `dbt build` has created data/warehouse.duckdb)
Reads only mart tables, read-only.
"""
import os
from pathlib import Path

import altair as alt
import duckdb
import streamlit as st

DB = os.environ.get("DUCKDB_PATH") or Path(__file__).resolve().parents[1] / "data" / "warehouse.duckdb"
SAVING_COLOUR = "#2a78d6"     # categorical slot 1 (blue)
LOW_VALUE_COLOUR = "#eb6834"  # categorical slot 2 (orange)
ANTIEPILEPTICS = "0408010"    # MHRA category 2 drugs sit here: flag for clinical review, don't auto-switch
# "NHS X INTEGRATED CARE BOARD" -> "X": the wrapper is identical on every ICB and eats label space
SHORT_ICB = "trim(replace(replace(icb_name, 'NHS ', ''), ' INTEGRATED CARE BOARD', ''))"

st.set_page_config(page_title="Medicines Value Monitor", page_icon="💊", layout="wide")


@st.cache_resource
def connect():
    return duckdb.connect(str(DB), read_only=True)


@st.cache_data
def query(sql: str, params: tuple = ()):
    return connect().execute(sql, list(params)).df()


def gbp(x: float) -> str:
    return f"£{x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"£{x / 1e3:,.0f}k"


def bar(df, x, y, colour, x_title, tooltip):
    return (
        alt.Chart(df)
        .mark_bar(color=colour, cornerRadiusEnd=4, size=14)
        .encode(
            x=alt.X(x, title=x_title),
            y=alt.Y(y, sort="-x", title=None, axis=alt.Axis(labelLimit=320, labelOverlap=False)),
            tooltip=tooltip,
        )
        .properties(height=max(200, 26 * len(df)))
    )


# ---------- filters ----------
months = query("select distinct month from mart_icb_monthly order by 1 desc")["month"]
icbs = query(f"select icb_code, {SHORT_ICB} as icb_name from dim_icb where icb_code <> '-' order by 2")

with st.sidebar:
    st.header("Filters")
    month = st.selectbox("Month", months, format_func=lambda d: d.strftime("%B %Y"))
    icb_name = st.selectbox("ICB", ["All England", *icbs["icb_name"]])
icb = None if icb_name == "All England" else icbs.loc[icbs["icb_name"] == icb_name, "icb_code"].item()
scope = "icb_code = ?" if icb else "true"
scope_params = (icb,) if icb else ()

st.title("Medicines Value Monitor")
st.caption(
    f"{icb_name} · {month:%B %Y} · NHSBSA English Prescribing Dataset. "
    "Potential saving = branded spend above the median generic price, excluding drugs that guidance says to prescribe by brand."
)

# ---------- KPIs ----------
k = query(
    f"select sum(nic) nic, sum(potential_saving) saving, sum(low_value_nic) low_value "
    f"from mart_icb_monthly where month = ? and {scope}",
    (month, *scope_params),
).iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Total spend (NIC)", gbp(k.nic))
c2.metric("Potential generic saving", gbp(k.saving), f"{100 * k.saving / k.nic:.2f}% of spend", delta_color="off", delta_arrow="off")
c3.metric("Low-value prescribing", gbp(k.low_value), f"£{1000 * k.low_value / k.nic:.2f} per £1k spend", delta_color="off", delta_arrow="off")

where_tab, drugs_tab, low_tab, trend_tab, method_tab = st.tabs(
    ["Where", "Which drugs", "Low-value items", "Trend", "Method"]
)

# ---------- where ----------
with where_tab:
    if icb is None:
        st.subheader("ICBs ranked by potential saving per £1,000 spent")
        df = query(
            f"select {SHORT_ICB} as icb_name, saving_per_1000_nic, potential_saving, low_value_per_1000_nic, nic "
            "from mart_icb_monthly where month = ? and icb_code <> '-' order by saving_per_1000_nic desc",
            (month,),
        )
        st.altair_chart(
            bar(df, "saving_per_1000_nic:Q", "icb_name:N", SAVING_COLOUR, "£ potential saving per £1,000 spend",
                [alt.Tooltip("icb_name:N", title="ICB"),
                 alt.Tooltip("saving_per_1000_nic:Q", title="£ per £1k", format=",.2f"),
                 alt.Tooltip("potential_saving:Q", title="Saving £", format=",.0f")]),
            width="stretch",
        )
    else:
        st.subheader(f"Practices in {icb_name} ranked by potential saving per £1,000 spent")
        min_spend = st.slider("Minimum practice spend (£k), to hide very small practices", 0, 200, 20, 10)
        df = query(
            "select practice_name, postcode, saving_per_1000_nic, potential_saving, low_value_per_1000_nic, nic "
            "from mart_practice_monthly where month = ? and icb_code = ? and practice_code <> '-' and nic >= ? "
            "order by saving_per_1000_nic desc limit 25",
            (month, icb, min_spend * 1000),
        )
        st.altair_chart(
            bar(df, "saving_per_1000_nic:Q", "practice_name:N", SAVING_COLOUR, "£ potential saving per £1,000 spend",
                [alt.Tooltip("practice_name:N", title="Practice"),
                 alt.Tooltip("saving_per_1000_nic:Q", title="£ per £1k", format=",.2f"),
                 alt.Tooltip("potential_saving:Q", title="Saving £", format=",.0f")]),
            width="stretch",
        )
    with st.expander("Table view"):
        st.dataframe(df, hide_index=True, width="stretch")

# ---------- drugs ----------
with drugs_tab:
    st.subheader("Where the saving is: top 15 drugs")
    df = query(
        f"""
        select coalesce(b.bnf_name, s.generic_equiv_code)
                   || case when starts_with(s.generic_equiv_code, '{ANTIEPILEPTICS}') then ' (review)' else '' end as drug,
               sum(s.potential_saving) as potential_saving,
               sum(s.nic)              as branded_spend,
               starts_with(s.generic_equiv_code, '{ANTIEPILEPTICS}') as needs_clinical_review
        from mart_branded_savings s
        left join dim_bnf b on b.bnf_code = s.generic_equiv_code
        where s.month = ? and {scope.replace('icb_code', 's.icb_code')}
        group by all
        order by potential_saving desc
        limit 15
        """,
        (month, *scope_params),
    )
    st.altair_chart(
        bar(df, "potential_saving:Q", "drug:N", SAVING_COLOUR, "£ potential saving",
            [alt.Tooltip("drug:N", title="Generic"),
             alt.Tooltip("potential_saving:Q", title="Saving £", format=",.0f"),
             alt.Tooltip("branded_spend:Q", title="Branded spend £", format=",.0f")]),
        width="stretch",
    )
    st.caption(
        "Names are the generic equivalent. Antiepileptics are marked (review): "
        "switching them is a prescriber's judgement (MHRA category 2), not an automatic saving."
    )
    with st.expander("Table view"):
        st.dataframe(df, hide_index=True, width="stretch")

# ---------- low value ----------
with low_tab:
    st.subheader("Spend on items that should not routinely be prescribed")
    df = query(
        f"select category, sum(items) as items, sum(nic) as spend from mart_low_value "
        f"where month = ? and {scope} group by 1 order by spend desc",
        (month, *scope_params),
    )
    st.altair_chart(
        bar(df, "spend:Q", "category:N", LOW_VALUE_COLOUR, "£ spend",
            [alt.Tooltip("category:N", title="Category"),
             alt.Tooltip("spend:Q", title="Spend £", format=",.0f"),
             alt.Tooltip("items:Q", title="Items", format=",.0f")]),
        width="stretch",
    )
    st.caption("Categories from NHS England's list of items which should not routinely be prescribed in primary care (21 of 23 covered).")
    with st.expander("Table view"):
        st.dataframe(df, hide_index=True, width="stretch")

# ---------- trend ----------
with trend_tab:
    df = query(
        f"select month, 1000 * sum(potential_saving) / sum(nic) as saving_per_1k, "
        f"1000 * sum(low_value_nic) / sum(nic) as low_value_per_1k "
        f"from mart_icb_monthly where {scope} group by 1 order by 1",
        scope_params,
    )
    left, right = st.columns(2)  # two charts, never two y-axes on one
    for col, field, colour, title in [
        (left, "saving_per_1k", SAVING_COLOUR, "Potential saving per £1,000 spend"),
        (right, "low_value_per_1k", LOW_VALUE_COLOUR, "Low-value spend per £1,000 spend"),
    ]:
        col.subheader(title)
        col.altair_chart(
            alt.Chart(df).mark_line(color=colour, strokeWidth=2, point=alt.OverlayMarkDef(size=64, color=colour))
            .encode(
                x=alt.X("yearmonth(month):T", title=None),
                y=alt.Y(f"{field}:Q", title="£", scale=alt.Scale(zero=True)),
                tooltip=[alt.Tooltip("yearmonth(month):T", title="Month"),
                         alt.Tooltip(f"{field}:Q", title="£ per £1k", format=",.2f")],
            ),
            width="stretch",
        )
    with st.expander("Table view"):
        st.dataframe(df, hide_index=True, width="stretch")

# ---------- method ----------
with method_tab:
    st.markdown(
        """
**Potential generic saving**: for every generic drug, the reference price per unit is the median of practices' own prices.
Branded prescribing of a drug whose generic is also prescribed is costed at that price; the saving is the difference,
floored at zero. Drugs that guidance says to prescribe by brand are excluded (inhalers, insulins, MHRA category 1
antiepileptics, ciclosporin/tacrolimus, lithium, some modified-release products, pancreatin).

**Low-value prescribing**: spend matching NHS England's list of items that should not routinely be prescribed in primary care,
with BNF codes taken from OpenPrescribing's published measure definitions.

**Rates** are per £1,000 of total spend, so areas of different sizes are comparable.

**Limitations**: reference prices are from practice data, not the Drug Tariff; per-patient rates need practice list sizes (not yet included);
2 of the 23 low-value categories are omitted. Full write-ups are in `docs/`.
"""
    )
