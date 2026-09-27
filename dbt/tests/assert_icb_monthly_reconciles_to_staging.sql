-- Total NIC per month in the headline mart must equal staging: no rows lost or double counted.
with stg as (select month, sum(nic) as nic from {{ ref('stg_epd') }} group by 1),
mart as (select month, sum(nic) as nic from {{ ref('mart_icb_monthly') }} group by 1)
select stg.month, stg.nic, mart.nic as mart_nic
from stg full join mart using (month)
where mart.nic is null or stg.nic is null or abs(stg.nic - mart.nic) > 0.01
