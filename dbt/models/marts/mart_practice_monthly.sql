-- Practice-level headline figures for drill-down. Grain: month x practice.
-- Rates are per 1,000 GBP of the practice's total spend so practices of different sizes are comparable.
with totals as (
    select month, icb_code, practice_code, sum(items) as items, sum(nic) as nic
    from {{ ref('stg_epd') }}
    group by all
),

savings as (
    select month, icb_code, practice_code, sum(potential_saving) as potential_saving
    from {{ ref('mart_branded_savings') }}
    group by all
),

low_value as (
    select month, icb_code, practice_code, sum(nic) as low_value_nic
    from {{ ref('mart_low_value') }}
    group by all
)

select
    t.month,
    t.icb_code,
    t.practice_code,
    p.practice_name,
    p.postcode,
    t.items,
    t.nic,
    coalesce(s.potential_saving, 0) as potential_saving,
    coalesce(l.low_value_nic, 0)    as low_value_nic,
    1000 * coalesce(s.potential_saving, 0) / nullif(t.nic, 0) as saving_per_1000_nic,
    1000 * coalesce(l.low_value_nic, 0) / nullif(t.nic, 0)    as low_value_per_1000_nic
from totals t
left join savings s using (month, icb_code, practice_code)
left join low_value l using (month, icb_code, practice_code)
left join {{ ref('dim_practice') }} p using (practice_code)
