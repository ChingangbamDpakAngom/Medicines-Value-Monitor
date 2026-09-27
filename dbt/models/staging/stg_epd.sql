-- One row per practice x BNF presentation x SNOMED code x quantity-per-item x month. Not unique: the source
-- splits rows by prescription size (e.g. 2 items of 60 and 4 items of 30), so use total_quantity for volumes.
-- Drug BNF codes (15 chars, chapters 01-19): 1-9 chemical, 10-11 product ('AA' = generic),
-- 12-13 strength/form, 14-15 generic equivalent. Appliances/dressings (chapters 20-23) use 11-char codes
-- with no generic structure, so generic fields are NULL for them.
with src as (
    select
        *,
        length(BNF_PRESENTATION_CODE) = 15 and left(BNF_PRESENTATION_CODE, 2) <= '19' as is_drug
    from {{ source('epd', 'epd_raw') }}
)

select
    strptime(YEAR_MONTH, '%Y-%m')::date                 as month,
    REGIONAL_OFFICE_CODE                                as region_code,
    REGIONAL_OFFICE_NAME                                as region_name,
    ICB_CODE                                            as icb_code,
    ICB_NAME                                            as icb_name,
    PCO_CODE                                            as pco_code,
    PCO_NAME                                            as pco_name,
    PRACTICE_CODE                                       as practice_code,
    PRACTICE_NAME                                       as practice_name,
    POSTCODE                                            as postcode,
    UNIDENTIFIED = 'Y'                                  as is_unidentified,
    BNF_CHAPTER_PLUS_CODE                               as bnf_chapter,
    BNF_CHEMICAL_SUBSTANCE_CODE                         as chemical_code,
    BNF_CHEMICAL_SUBSTANCE                              as chemical_name,
    BNF_PRESENTATION_CODE                               as bnf_code,
    BNF_PRESENTATION_NAME                               as bnf_name,
    SNOMED_CODE                                         as snomed_code,
    is_drug,
    case when is_drug then substr(BNF_PRESENTATION_CODE, 10, 2) = 'AA' end
                                                        as is_generic,
    case when is_drug then
        substr(BNF_PRESENTATION_CODE, 1, 9) || 'AA'
        || substr(BNF_PRESENTATION_CODE, 14, 2)
        || substr(BNF_PRESENTATION_CODE, 14, 2)
    end                                                 as generic_equiv_code,
    ITEMS                                               as items,
    QUANTITY                                            as quantity_per_item,
    TOTAL_QUANTITY                                      as total_quantity,
    ADQ_USAGE                                           as adq_usage,
    NIC                                                 as nic,
    ACTUAL_COST                                         as actual_cost
from src
