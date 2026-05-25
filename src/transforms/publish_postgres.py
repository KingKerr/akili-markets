import os
import duckdb
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.dialects.postgresql import ARRAY, TEXT

DUCKDB_PATH = "data/stage/market.duckdb"

def postgres_url():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    missing = [k for k, v in {
        "POSTGRES_HOST": host,
        "POSTGRES_PORT": port,
        "POSTGRES_DB": db,
        "POSTGRES_USER": user,
        "POSTGRES_PASSWORD": password,
    }.items() if not v or v == "None"]

    if missing:
        raise ValueError(f"Missing required Postgres env vars: {', '.join(missing)}")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

def get_engine():
    return create_engine(postgres_url())

def load_df(con, query: str) -> pd.DataFrame:
    return con.execute(query).df()

def safe_load_df(con, query: str) -> pd.DataFrame:
    try:
        return load_df(con, query)
    except Exception as e:
        print(f"[skip] source query failed: {e}")
        return pd.DataFrame()


def skip_if_empty(df: pd.DataFrame, label: str) -> bool:
    if df is None or df.empty:
        print(f"[skip] {label}: no rows to publish")
        return True
    return False

def existing_dim_tickers(engine) -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(text("select ticker from dim_ticker")).fetchall()
    return {r[0] for r in rows}

def upsert_dataframe(engine, df, target_table, temp_table, conflict_cols, update_cols, dtype_map=None):
    if df is None or df.empty:
        print(f"[skip] {target_table}: empty dataframe")
        return 0

    df.to_sql(
        temp_table, 
        engine, 
        if_exists="replace", 
        index=False, 
        dtype=dtype_map or {},
    )

    insert_cols = list(df.columns)
    insert_cols_sql = ", ".join(insert_cols)
    conflict_cols_sql = ", ".join(conflict_cols)
    update_sql = ", ".join([f"{col} = excluded.{col}" for col in update_cols])

    sql = f"""
        insert into {target_table} ({insert_cols_sql})
        select {insert_cols_sql}
        from {temp_table}
        on conflict ({conflict_cols_sql})
        do update set {update_sql}
    """

    with engine.begin() as conn:
        conn.execute(text(sql))

    print(f"[ok] {target_table}: upserted {len(df)} rows")
    return len(df)
"""
----------------------------
Publishing Dimension Tables
----------------------------
"""
def publish_dim_date(con, engine):
    df = safe_load_df(con, """
        select
          date_day,
          year_num,
          quarter_num,
          month_num,
          month_name,
          week_num,
          day_of_month,
          day_of_week,
          day_name,
          is_month_end,
          is_quarter_end,
          is_year_end
        from dim_date_stage
        order by date_day
    """)

    if skip_if_empty(df, "dim_date"):
        return 0

    return upsert_dataframe(
        engine, df, "dim_date", "_tmp_dim_date",
        ["date_day"],
        [
            "year_num",
            "quarter_num",
            "month_num",
            "month_name",
            "week_num",
            "day_of_month",
            "day_of_week",
            "day_name",
            "is_month_end",
            "is_quarter_end",
            "is_year_end"
        ]
    )

def publish_dim_ticker(con, engine):
    df = safe_load_df(con, """
        select
          ticker,
          company_name,
          null::varchar as primary_exchange,
          null::varchar as sector,
          null::varchar as industry,
          null::varchar as sic_code,
          null::bigint as market_cap,
          null::varchar as cik,
          null::varchar as locale,
          null::varchar as currency_name,
          active,
          null::date as listing_date,
          current_timestamp as updated_at
        from stg_tickers
        where ticker is not null
    """)

    if skip_if_empty(df, "dim_ticker"):
        return 0

    return upsert_dataframe(
        engine, df, "dim_ticker", "_tmp_dim_ticker",
        ["ticker"],
        [
            "company_name",
            "primary_exchange",
            "sector",
            "industry",
            "sic_code",
            "market_cap",
            "cik",
            "locale",
            "currency_name",
            "active",
            "listing_date",
            "updated_at",
        ],
    )

"""
-------------------------
Backfills for Dim Date
-------------------------
"""
def backfill_dim_date_from_staging(engine, con):
    staged = safe_load_df(con, """
        select distinct date_day
        from (
            select cast(trade_date as date) as date_day from mart_price_features
            union
            select cast(published_at as date) as date_day from stg_news
            union
            select cast(filing_date as date) as date_day from stg_filing_sections
            union
            select cast(filing_date as date) as date_day from stg_risk_factors
        ) d
        where date_day is not null
        order by date_day
    """)

    if staged.empty:
        print("[skip] dim_date backfill: no staged dates")
        return 0

    df = staged.copy()
    df["date_day"] = pd.to_datetime(df["date_day"])
    df["year"] = df["date_day"].dt.year
    df["quarter"] = df["date_day"].dt.quarter
    df["month"] = df["date_day"].dt.month
    df["day_of_month"] = df["date_day"].dt.day
    df["day_of_week"] = df["date_day"].dt.dayofweek + 1
    df["is_weekend"] = df["day_of_week"].isin([6, 7])
    df["date_day"] = df["date_day"].dt.date

    return upsert_dataframe(
        engine,
        df,
        "dim_date",
        "_tmp_dim_date_backfill",
        ["date_day"],
        [
            "year",
            "quarter",
            "month",
            "day_of_month",
            "day_of_week",
            "is_weekend",
        ],
    )

"""
-------------------------
Backfills for Dim Ticker
-------------------------
"""
def backfill_dim_ticker_from_staging(engine, con):
    staged = safe_load_df(con, """
        select distinct ticker from (
            select ticker from mart_price_features
            union
            select ticker from stg_news
            union
            select ticker from stg_filing_sections
            union
            select ticker from stg_risk_factors
        ) t
        where ticker is not null
    """)

    if staged.empty:
        print("[skip] dim_ticker backfill: no staged tickers")
        return 0

    with engine.begin() as conn:
        existing = {
            row[0]
            for row in conn.execute(text("select ticker from dim_ticker")).fetchall()
        }

        missing = sorted(set(staged["ticker"]) - existing)

        if not missing:
            print("[ok] dim_ticker backfill: no missing tickers")
            return 0
        
        for ticker in missing:
            conn.execute(text("""
                insert into dim_ticker (
                    ticker,
                    company_name,
                    primary_exchange,
                    sector,
                    industry,
                    sic_code,
                    market_cap,
                    cik,
                    locale,
                    currency_name,
                    active,
                    listing_date,
                    updated_at
                )
                values (
                    :ticker,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    current_timestamp
                )
                on conflict (ticker) do nothing
            """), {"ticker": ticker})
    print(f"[ok] dim_ticker backfill: inserted {len(missing)} placeholder tickers")
    return len(missing)

# Adding a dependency check before proceeding with publishing
# This will help prevent any failures due to a FK not being loaded for fact_price_daily
"""
def dim_ticker_ready(engine) -> bool:
    with engine.begin() as conn:
        result = conn.execute(text("select count(*) from dim_ticker")).scalar()
    return result > 0
"""
"""
---------------------
Publishing Fact Tables
---------------------
"""
def publish_fact_price_daily(con, engine):
    df = safe_load_df(con, """
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
          return_1d,
          return_5d,
          volatility_20d,
          volume_vs_20d,
          gap_from_prev_close,
          current_timestamp as created_at
        from mart_price_features
        where ticker is not null
    """)

    if skip_if_empty(df, "fact_price_daily"):
        return 0

    return upsert_dataframe(
        engine, df, "fact_price_daily", "_tmp_fact_price_daily",
        ["ticker", "trade_date"],
        [
            "bar_timestamp",
            "adjusted",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vwap",
            "transactions",
            "return_1d",
            "return_5d",
            "volatility_20d",
            "volume_vs_20d",
            "gap_from_prev_close"
        ]
    )

def normalize_array_value(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if x is None:
        return []
    if isinstance(x, float) and pd.isna(x):
        return []
    return x


def publish_fact_news(con, engine):
    df = safe_load_df(con, """
        select distinct
          news_id,
          ticker,
          published_at,
          publisher_name as publisher,
          publisher_homepage_url,
          publisher_logo_url,
          publisher_favicon_url,
          title,
          summary,
          article_url,
          amp_url,
          author,
          image_url,
          sentiment,
          sentiment_reasoning,
          keywords,
          current_timestamp as created_at
        from stg_news
        where news_id is not null
          and ticker is not null
    """)

    if skip_if_empty(df, "fact_news"):
        return 0
    
    if "keywords" in df.columns:
        df["keywords"] = df["keywords"].apply(normalize_array_value)

    valid_tickers = existing_dim_tickers(engine)
    before = len(df)
    df = df[df["ticker"].isin(valid_tickers)].copy()
    skipped = before - len(df)

    if skipped:
        print(f"[skip] fact_news: filtered out {skipped} rows with unknown tickers")
    
    if skip_if_empty(df, "fact_news after ticker filter"):
        return 0

    return upsert_dataframe(
        engine, df, "fact_news", "_tmp_fact_news",
        ["news_id", "ticker"],
        [
            "published_at",
            "publisher",
            "publisher_homepage_url",
            "publisher_logo_url",
            "publisher_favicon_url",
            "title",
            "summary",
            "article_url",
            "amp_url",
            "author",
            "image_url",
            "sentiment",
            "sentiment_reasoning",
            "keywords"
        ], 
        dtype_map = {
            "keywords": ARRAY(TEXT)
        }
    )

def publish_fact_filing_section(con, engine):
    df = safe_load_df(con, """
        select
          filing_id,
          ticker,
          cik,
          filing_date,
          period_end,
          form_type,
          section_name,
          section_text,
          source_url,
          current_timestamp as created_at
        from stg_filing_sections
        where filing_id is not null
          and ticker is not null
          and section_name is not null
    """)

    if skip_if_empty(df, "fact_filing_section"):
        return 0

    return upsert_dataframe(
        engine, df, "fact_filing_section", "_tmp_fact_filing_section",
        ["filing_id", "section_name"],
        [
            "ticker",
            "cik",
            "filing_date",
            "period_end",
            "form_type",
            "section_text",
            "source_url"
        ]
    )

def publish_fact_risk_factor(con, engine):
    df = safe_load_df(con, """
        select
          risk_factor_id,
          ticker,
          cik,
          filing_date,
          category_level_1,
          category_level_2,
          category_level_3,
          null as risk_title,
          risk_text,
          null as source_filing_id,
          current_timestamp as created_at
        from stg_risk_factors
        where risk_factor_id is not null
          and ticker is not null
    """)

    if skip_if_empty(df, "fact_risk_factor"):
        return 0

    return upsert_dataframe(
        engine, df, "fact_risk_factor", "_tmp_fact_risk_factor",
        ["risk_factor_id"],
        [
            "ticker",
            "cik",
            "filing_date",
            "category_level_1",
            "category_level_2",
            "category_level_3",
            "risk_title",
            "risk_text",
            "source_filing_id"
        ]
    )

def main():
    con = duckdb.connect(DUCKDB_PATH)
    engine = create_engine(postgres_url())
    # Publish Dimensions First
    #publish_dim_date(con, engine)
    publish_dim_ticker(con, engine)

    # Perform Backfill in case any dates & tickers are missing from staged Facts
    backfill_dim_date_from_staging(engine, con)
    backfill_dim_ticker_from_staging(engine, con)
    """
    if dim_ticker_ready(engine):
        publish_fact_price_daily(con, engine)
    else:
        print("[skip] fact_price_daily: dim_ticker is empty")
    """
    # Now publish Facts
    publish_fact_price_daily(con, engine)
    publish_fact_news(con, engine)
    publish_fact_filing_section(con, engine)
    publish_fact_risk_factor(con, engine)

    print("Postgres publish complete.")

if __name__ == "__main__":
    main()