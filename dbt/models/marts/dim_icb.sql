-- One row per ICB, with its most recent name and region.
select
    icb_code,
    arg_max(icb_name, month)    as icb_name,
    arg_max(region_name, month) as region_name
from {{ ref('stg_epd') }}
group by 1
