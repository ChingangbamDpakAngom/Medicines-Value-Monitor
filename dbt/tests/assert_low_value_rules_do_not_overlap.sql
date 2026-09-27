-- A presentation must match at most one inclusion rule, otherwise mart_low_value double counts it.
select s.bnf_code, count(*) as n_rules
from (select distinct bnf_code from {{ ref('stg_epd') }}) s
join {{ ref('low_value_medicines') }} r
  on s.bnf_code like r.bnf_code_like and not r.is_exclusion
group by 1
having count(*) > 1
