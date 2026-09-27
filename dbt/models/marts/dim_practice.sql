-- One row per practice, with its most recent name, postcode and ICB.
select
    practice_code,
    arg_max(practice_name, month) as practice_name,
    arg_max(postcode, month)      as postcode,
    arg_max(icb_code, month)      as icb_code,
    arg_max(icb_name, month)      as icb_name,
    arg_max(region_name, month)   as region_name
from {{ ref('stg_epd') }}
group by 1
