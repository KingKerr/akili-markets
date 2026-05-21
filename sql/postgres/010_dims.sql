create table if not exists dim_ticker (
  ticker text primary key,
  company_name text,
  primary_exchange text,
  sector text,
  industry text,
  sic_code text,
  market_cap numeric,
  cik text,
  locale text,
  currency_name text,
  active boolean,
  listing_date date,
  updated_at timestamptz default now()
);

create table if not exists dim_date (
  date_day date primary key,
  year int,
  quarter int,
  month int,
  day_of_month int,
  day_of_week int,
  is_weekend boolean
);

create table if not exists bridge_ticker_peer (
  ticker text not null references dim_ticker(ticker),
  peer_ticker text not null references dim_ticker(ticker),
  relationship_score numeric,
  source text,
  as_of_date date,
  primary key (ticker, peer_ticker, as_of_date)
);