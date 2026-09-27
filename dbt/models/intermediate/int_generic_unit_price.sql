-- Reference price per unit for each generic presentation per month.
-- Price per practice first (rows are split by prescription size, so aggregate before dividing),
-- then the median across practices so no single practice sets the reference.
with practice_price as (
    select
        month,
        bnf_code,
        practice_code,
        sum(nic) / sum(total_quantity) as price_per_unit
    from {{ ref('stg_epd') }}
    where is_generic and not is_unidentified
    group by all
    having sum(total_quantity) > 0
)

select
    month,
    bnf_code                as generic_code,
    median(price_per_unit)  as generic_price_per_unit,
    count(*)                as n_practices
from practice_price
group by all
