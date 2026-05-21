create or replace view mart_price_features as
select
  ticker,
  trade_date,
  close,
  volume,
  return_1d,
  return_5d,
  volatility_20d,
  volume_vs_20d,
  gap_from_prev_close
from fact_price_daily;

create or replace view mart_latest_risk_summary as
with latest_filing as (
  select ticker, max(filing_date) as filing_date
  from fact_risk_factor
  group by 1
)
select
  r.ticker,
  r.category_level_1,
  count(*) as risk_count
from fact_risk_factor r
join latest_filing lf
  on r.ticker = lf.ticker
 and r.filing_date = lf.filing_date
group by 1, 2;

create or replace view mart_recent_news_counts as
select
  ticker,
  date_trunc('day', published_at)::date as news_date,
  count(*) as article_count
from fact_news
group by 1, 2;