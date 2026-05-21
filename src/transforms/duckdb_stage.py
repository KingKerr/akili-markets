import os
import duckdb
from pathlib import Path

DB_PATH = "data/stage/market.duckdb"

def ensure_dirs():
    os.makedirs("data/stage", exist_ok=True)

def has_files(pattern: str) -> bool:
    return any(Path(".").glob(pattern))

def run_sql(con, sql_path):
    with open(sql_path, "r") as f:
        sql = f.read()
    con.execute(sql)

def build_dates(con):
    con.execute("""
        create or replace table stg_dates as
        with dates as (
          select * from generate_series(date '2024-01-01', current_date, interval 1 day)
        )
        select
          generate_series as date_day,
          year(generate_series) as year,
          quarter(generate_series) as quarter,
          month(generate_series) as month,
          day(generate_series) as day_of_month,
          dayofweek(generate_series) as day_of_week,
          case when dayofweek(generate_series) in (0, 6) then true else false end as is_weekend
        from dates
    """)

def build_price_features(con):
    con.execute("""
        create or replace table mart_price_features as
        with base as (
          select
            ticker,
            trade_date,
            bar_timestamp,
            adjusted,
            open,
            high,
            low,
            close,
            volume,
            vwap,
            transactions,
            lag(close) over (
              partition by ticker
              order by trade_date
            ) as prev_close,
            lag(close, 5) over (
              partition by ticker
              order by trade_date
            ) as close_5d_ago,
            avg(volume) over (
              partition by ticker
              order by trade_date
              rows between 19 preceding and current row
            ) as avg_volume_20d,
            stddev_samp(close) over (
              partition by ticker
              order by trade_date
              rows between 19 preceding and current row
            ) as volatility_20d
          from stg_ticker_aggs
          where ticker is not null
        )
        select
          ticker,
          trade_date,
          bar_timestamp,
          adjusted,
          open,
          high,
          low,
          close,
          volume,
          vwap,
          transactions,
          case
            when prev_close is null or prev_close = 0 then null
            else (close / prev_close) - 1.0
          end as return_1d,
          case
            when close_5d_ago is null or close_5d_ago = 0 then null
            else (close / close_5d_ago) - 1.0
          end as return_5d,
          volatility_20d,
          case
            when avg_volume_20d is null or avg_volume_20d = 0 then null
            else volume / avg_volume_20d
          end as volume_vs_20d,
          case
            when prev_close is null or prev_close = 0 then null
            else (open / prev_close) - 1.0
          end as gap_from_prev_close
        from base
    """)

def build_news_stage(con):
    if not has_files("data/raw/news/**/*.json"):
        con.execute("""
            create or replace table stg_news (
              news_id varchar,
              ticker varchar,
              published_at timestamp,
              title varchar,
              summary varchar,
              article_url varchar,
              amp_url varchar,
              author varchar,
              image_url varchar,
              publisher_name varchar,
              publisher_homepage_url varchar,
              publisher_logo_url varchar,
              publisher_favicon_url varchar,
              sentiment varchar,
              sentiment_reasoning varchar,
              keywords varchar[]
            )
        """)
        return

    con.execute("""
        create or replace table stg_news as
        with raw as (
          select *
          from read_json_auto(
            'data/raw/news/**/*.json',
            maximum_object_size=100000000
          )
        ),
        articles as (
          select
            json_extract_string(j.value, '$.id') as news_id,
            try_cast(json_extract_string(j.value, '$.published_utc') as timestamp) as published_at,
            json_extract_string(j.value, '$.title') as title,
            json_extract_string(j.value, '$.description') as summary,
            json_extract_string(j.value, '$.article_url') as article_url,
            json_extract_string(j.value, '$.amp_url') as amp_url,
            json_extract_string(j.value, '$.author') as author,
            json_extract_string(j.value, '$.image_url') as image_url,
            json_extract_string(j.value, '$.publisher.name') as publisher_name,
            json_extract_string(j.value, '$.publisher.homepage_url') as publisher_homepage_url,
            json_extract_string(j.value, '$.publisher.logo_url') as publisher_logo_url,
            json_extract_string(j.value, '$.publisher.favicon_url') as publisher_favicon_url,
            j.value as article_json
          from raw,
          lateral json_each(raw.results) j
        ),
        article_tickers as (
          select
            a.*,
            json_extract_string(t.value, '$') as ticker
          from articles a,
          lateral json_each(json_extract(a.article_json, '$.tickers')) t
        ),
        article_keywords as (
          select
            a.news_id,
            list(json_extract_string(k.value, '$')) as keywords
          from articles a,
          lateral json_each(json_extract(a.article_json, '$.keywords')) k
          group by 1
        ),
        article_insights as (
          select
            a.news_id,
            json_extract_string(i.value, '$.ticker') as insight_ticker,
            json_extract_string(i.value, '$.sentiment') as sentiment,
            json_extract_string(i.value, '$.sentiment_reasoning') as sentiment_reasoning
          from articles a,
          lateral json_each(json_extract(a.article_json, '$.insights')) i
        )
        select
          art.news_id,
          art.ticker,
          art.published_at,
          art.title,
          art.summary,
          art.article_url,
          art.amp_url,
          art.author,
          art.image_url,
          art.publisher_name,
          art.publisher_homepage_url,
          art.publisher_logo_url,
          art.publisher_favicon_url,
          ai.sentiment,
          ai.sentiment_reasoning,
          coalesce(ak.keywords, []::varchar[]) as keywords
        from article_tickers art
        left join article_keywords ak
          on art.news_id = ak.news_id
        left join article_insights ai
          on art.news_id = ai.news_id
         and art.ticker = ai.insight_ticker
    """)

def build_10k_stage(con):
    if not has_files("data/raw/filings_10k_sections/**/*.json"):
        con.execute("""
            create or replace table stg_filing_sections (
              filing_id varchar,
              ticker varchar,
              cik varchar,
              filing_date date,
              period_end date,
              form_type varchar,
              section_name varchar,
              section_text varchar,
              source_url varchar
            )
        """)
        return

    con.execute("""
        create or replace table stg_filing_sections as
        with raw as (
          select *
          from read_json_auto(
            'data/raw/filings_10k_sections/**/*.json',
            maximum_object_size=100000000
          )
        )
        select
          md5(
            coalesce(json_extract_string(j.value, '$.ticker'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.cik'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.filing_date'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.period_end'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.section'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.filing_url'), '')
          ) as filing_id,
          json_extract_string(j.value, '$.ticker') as ticker,
          json_extract_string(j.value, '$.cik') as cik,
          cast(json_extract_string(j.value, '$.filing_date') as date) as filing_date,
          cast(json_extract_string(j.value, '$.period_end') as date) as period_end,
          '10-K' as form_type,
          json_extract_string(j.value, '$.section') as section_name,
          json_extract_string(j.value, '$.text') as section_text,
          json_extract_string(j.value, '$.filing_url') as source_url
        from raw,
        lateral json_each(raw.results) j
    """)

def build_risk_stage(con):
    if not has_files("data/raw/risk_factors/**/*.json"):
        con.execute("""
            create or replace table stg_risk_factors (
              ticker varchar,
              cik varchar,
              filing_date date,
              category_level_1 varchar,
              category_level_2 varchar,
              category_level_3 varchar,
              risk_text varchar,
              risk_factor_id varchar
            )
        """)
        return

    con.execute("""
        create or replace table stg_risk_factors as
        with raw as (
          select *
          from read_json_auto(
            'data/raw/risk_factors/**/*.json',
            maximum_object_size=100000000
          )
        )
        select
          json_extract_string(j.value, '$.ticker') as ticker,
          json_extract_string(j.value, '$.cik') as cik,
          cast(json_extract_string(j.value, '$.filing_date') as date) as filing_date,
          json_extract_string(j.value, '$.primary_category') as category_level_1,
          json_extract_string(j.value, '$.secondary_category') as category_level_2,
          json_extract_string(j.value, '$.tertiary_category') as category_level_3,
          json_extract_string(j.value, '$.supporting_text') as risk_text,
          md5(
            coalesce(json_extract_string(j.value, '$.ticker'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.cik'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.filing_date'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.primary_category'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.secondary_category'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.tertiary_category'), '') || '|' ||
            coalesce(json_extract_string(j.value, '$.supporting_text'), '')
          ) as risk_factor_id
        from raw,
        lateral json_each(raw.results) j
    """)

def build_ticker_aggs_stage(con):
    if not has_files("data/raw/aggs_ticker/**/*.json"):
        con.execute("""
            create or replace table stg_ticker_aggs (
              ticker varchar,
              adjusted boolean,
              bar_timestamp timestamp,
              trade_date date,
              open double,
              high double,
              low double,
              close double,
              volume bigint,
              vwap double,
              transactions bigint
            )
        """)
        return

    con.execute("""
        create or replace table stg_ticker_aggs as
        with raw as (
          select *
          from read_json_auto(
            'data/raw/aggs_ticker/**/*.json',
            maximum_object_size=100000000
          )
        ),
        payloads as (
          select to_json(raw) as data
          from raw
        )
        select
          json_extract_string(p.data, '$.ticker') as ticker,
          cast(json_extract(p.data, '$.adjusted') as boolean) as adjusted,
          epoch_ms(cast(json_extract(j.value, '$.t') as bigint)) as bar_timestamp,
          cast(epoch_ms(cast(json_extract(j.value, '$.t') as bigint)) as date) as trade_date,
          cast(json_extract(j.value, '$.o') as double) as open,
          cast(json_extract(j.value, '$.h') as double) as high,
          cast(json_extract(j.value, '$.l') as double) as low,
          cast(json_extract(j.value, '$.c') as double) as close,
          cast(json_extract(j.value, '$.v') as bigint) as volume,
          cast(json_extract(j.value, '$.vw') as double) as vwap,
          cast(json_extract(j.value, '$.n') as bigint) as transactions
        from payloads p,
        lateral json_each(json_extract(p.data, '$.results')) j
    """)

def main():
    ensure_dirs()
    con = duckdb.connect(DB_PATH)
    run_sql(con, "sql/duckdb/stage.sql")
    build_dates(con)
    build_ticker_aggs_stage(con)
    build_price_features(con)
    build_news_stage(con)
    build_10k_stage(con)
    build_risk_stage(con)
    print("DuckDB staging complete.")

if __name__ == "__main__":
    main()