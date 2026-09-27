-- One row per BNF presentation, with its most recent name, chemical and chapter.
select
    bnf_code,
    arg_max(bnf_name, month)      as bnf_name,
    arg_max(chemical_name, month) as chemical_name,
    arg_max(bnf_chapter, month)   as bnf_chapter
from {{ ref('stg_epd') }}
group by 1
