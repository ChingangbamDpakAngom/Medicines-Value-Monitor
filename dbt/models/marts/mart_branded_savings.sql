-- Potential saving had branded drugs been prescribed generically at the reference generic price.
-- Grain: month x practice x generic equivalent. Drugs where brand prescribing is appropriate
-- (brand_exceptions seed) are excluded; brands cheaper than the generic count as zero saving.
with branded as (
    select
        s.month,
        s.icb_code,
        s.practice_code,
        s.generic_equiv_code,
        sum(s.items)          as items,
        sum(s.total_quantity) as total_quantity,
        sum(s.nic)            as nic
    from {{ ref('stg_epd') }} s
    where s.is_drug
      and not s.is_generic
      and not exists (
          select 1 from {{ ref('brand_exceptions') }} x
          where s.bnf_code like x.bnf_code_like
      )
    group by all
)

select
    b.*,
    p.generic_price_per_unit,
    greatest(b.nic - b.total_quantity * p.generic_price_per_unit, 0)   as potential_saving
from branded b
join {{ ref('int_generic_unit_price') }} p
  on p.month = b.month
 and p.generic_code = b.generic_equiv_code
