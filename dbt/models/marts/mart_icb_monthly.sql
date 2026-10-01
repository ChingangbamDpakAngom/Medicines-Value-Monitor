-- Dashboard headline table. Grain: month x ICB. Rolled up from mart_practice_monthly.
-- Rates are per 1,000 GBP of total spend so large and small ICBs are comparable.
with totals as (
    select month, icb_code, sum(nic) as nic, sum(potential_saving) as potential_saving, sum(low_value_nic) as low_value_nic
    from {{ ref('mart_practice_monthly') }}
    group by all
)

select
    t.month,
    t.icb_code,
    i.icb_name,
    t.nic,
    t.potential_saving,
    t.low_value_nic,
    1000 * t.potential_saving / t.nic as saving_per_1000_nic,
    1000 * t.low_value_nic / t.nic    as low_value_per_1000_nic
from totals t
left join {{ ref('dim_icb') }} i using (icb_code)
