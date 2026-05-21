create or replace table stg_tickers as
select
  json_extract_string(j.value, '$.ticker') as ticker,
  json_extract_string(j.value, '$.name') as company_name,
  json_extract_string(j.value, '$.primary_exchange') as primary_exchange,
  json_extract_string(j.value, '$.locale') as locale,
  json_extract_string(j.value, '$.currency_name') as currency_name,
  cast(json_extract(j.value, '$.active') as boolean) as active
from read_json_auto('data/raw/reference_tickers/*.json') t,
lateral json_each(t.results) j;
