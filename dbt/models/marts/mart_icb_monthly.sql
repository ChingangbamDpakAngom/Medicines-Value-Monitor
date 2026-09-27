-- Dashboard headline table. Grain: month x ICB.
-- Rates are per 1,000 GBP of total spend so large and small ICBs are comparable.
with totals as (
    select
        month,
        icb_code,
        count(distinct practice_code) as practices,
        sum(items)                    as items,
        sum(nic)                      as nic
    from {{ ref('stg_epd') }}
    group by all
),

savings as (
    select month, icb_code, sum(nic) as branded_nic, sum(potential_saving) as potential_saving
    from {{ ref('mart_branded_savings') }}
    group by all
),

low_value as (
    select month, icb_code, sum(items) as low_value_items, sum(nic) as low_value_nic
    from {{ ref('mart_low_value') }}
    group by all
)

select
    t.month,
    t.icb_code,
    i.icb_name,
    i.region_name,
    t.practices,
    t.items,
    t.nic,
    coalesce(s.branded_nic, 0)          as branded_nic_with_generic,
    coalesce(s.potential_saving, 0)     as potential_saving,
    coalesce(l.low_value_items, 0)      as low_value_items,
    coalesce(l.low_value_nic, 0)        as low_value_nic,
    1000 * coalesce(s.potential_saving, 0) / t.nic as saving_per_1000_nic,
    1000 * coalesce(l.low_value_nic, 0) / t.nic    as low_value_per_1000_nic
from totals t
left join {{ ref('dim_icb') }} i using (icb_code)
left join savings s using (month, icb_code)
left join low_value l using (month, icb_code)
