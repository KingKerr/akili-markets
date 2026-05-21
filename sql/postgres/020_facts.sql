create table if not exists fact_price_daily (
  ticker text not null references dim_ticker(ticker),
  trade_date date not null references dim_date(date_day),
  bar_timestamp timestamptz,
  adjusted boolean,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  volume bigint,
  vwap numeric,
  transactions bigint,
  return_1d numeric,
  return_5d numeric,
  volatility_20d numeric,
  volume_vs_20d numeric,
  gap_from_prev_close numeric,
  created_at timestamptz default now(),
  primary key (ticker, trade_date)
);

create table if not exists fact_news (
  news_id text not null,
  ticker text not null references dim_ticker(ticker),
  published_at timestamptz not null,
  publisher text,
  publisher_homepage_url text,
  publisher_logo_url text,
  publisher_favicon_url text,
  title text,
  summary text,
  article_url text,
  amp_url text,
  author text,
  image_url text,
  sentiment text,
  sentiment_reasoning text,
  keywords text[],
  created_at timestamptz default now(),
  primary key (news_id, ticker)
);

create table if not exists fact_filing_section (
  filing_id text not null,
  ticker text not null references dim_ticker(ticker),
  cik text,
  filing_date date not null,
  period_end date,
  form_type text not null,
  section_name text not null,
  section_text text not null,
  source_url text,
  created_at timestamptz default now(),
  primary key (filing_id, section_name)
);

create table if not exists fact_risk_factor (
  risk_factor_id text primary key,
  ticker text not null references dim_ticker(ticker),
  cik text,
  filing_date date not null,
  category_level_1 text,
  category_level_2 text,
  category_level_3 text,
  risk_title text,
  risk_text text,
  source_filing_id text,
  created_at timestamptz default now()
);

create table if not exists pipeline_run (
  run_id uuid primary key default gen_random_uuid(),
  job_name text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null,
  row_count int,
  details jsonb
);

create table if not exists data_quality_result (
  check_name text not null,
  checked_at timestamptz not null default now(),
  status text not null,
  failing_rows int,
  details jsonb,
  primary key (check_name, checked_at)
);