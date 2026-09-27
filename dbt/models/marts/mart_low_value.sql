-- Spend on items NHS England says should not routinely be prescribed in primary care.
-- Grain: month x practice x category. A presentation counts if it matches an inclusion rule
-- and no exclusion rule (e.g. topical NSAIDs are excluded from rubefacients).
with rules as (
    select * from {{ ref('low_value_medicines') }}
),

matched as (
    select
        s.month,
        s.icb_code,
        s.practice_code,
        r.category,
        s.items,
        s.nic
    from {{ ref('stg_epd') }} s
    join rules r
      on s.bnf_code like r.bnf_code_like
     and not r.is_exclusion
    where not exists (
        select 1 from rules x
        where x.is_exclusion and s.bnf_code like x.bnf_code_like
    )
)

select
    month,
    icb_code,
    practice_code,
    category,
    sum(items) as items,
    sum(nic)   as nic
from matched
group by all
