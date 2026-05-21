import os
from sqlalchemy import create_engine, text

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def latest_metrics(conn, ticker):
    row = conn.execute(text("""
        select
          ticker,
          trade_date,
          close,
          return_1d,
          return_5d,
          volatility_20d,
          volume_vs_20d
        from fact_price_daily
        where ticker = :ticker
        order by trade_date desc
        limit 1
    """), {"ticker": ticker}).mappings().first()
    return dict(row) if row else {}

def risk_counts(conn, ticker):
    rows = conn.execute(text("""
        with latest_filing as (
          select max(filing_date) as filing_date
          from fact_risk_factor
          where ticker = :ticker
        )
        select
          category_level_1,
          count(*) as risk_count
        from fact_risk_factor
        where ticker = :ticker
          and filing_date = (select filing_date from latest_filing)
        group by 1
        order by 2 desc
    """), {"ticker": ticker}).mappings().all()
    return [dict(r) for r in rows]

def compare_tickers(ticker_a, ticker_b):
    engine = get_engine()
    with engine.begin() as conn:
        return {
            "ticker_a": latest_metrics(conn, ticker_a),
            "ticker_b": latest_metrics(conn, ticker_b),
            "risk_counts_a": risk_counts(conn, ticker_a),
            "risk_counts_b": risk_counts(conn, ticker_b),
        }