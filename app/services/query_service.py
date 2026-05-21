import os
from sqlalchemy import create_engine, text

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def get_dashboard_data():
    engine = get_engine()
    watchlist = os.getenv("WATCHLIST", "NFLX,DIS,WBD,ROKU,SPOT").split(",")

    with engine.begin() as conn:
        rows = conn.execute(text("""
            select distinct on (ticker)
              ticker,
              trade_date,
              close,
              return_1d,
              return_5d,
              volume_vs_20d
            from fact_price_daily
            where ticker = any(:watchlist)
            order by ticker, trade_date desc
        """), {"watchlist": watchlist}).mappings().all()

    return {"watchlist_metrics": [dict(r) for r in rows]}

def get_ticker_page_data(ticker):
    engine = get_engine()

    with engine.begin() as conn:
        prices = conn.execute(text("""
            select trade_date, close, return_1d, volume, volume_vs_20d
            from fact_price_daily
            where ticker = :ticker
            order by trade_date desc
            limit 30
        """), {"ticker": ticker}).mappings().all()

        news = conn.execute(text("""
            select published_at, title, summary, article_url
            from fact_news
            where ticker = :ticker
            order by published_at desc
            limit 10
        """), {"ticker": ticker}).mappings().all()

        risks = conn.execute(text("""
            with latest_filing as (
              select max(filing_date) as filing_date
              from fact_risk_factor
              where ticker = :ticker
            )
            select category_level_1, category_level_2, risk_title
            from fact_risk_factor
            where ticker = :ticker
              and filing_date = (select filing_date from latest_filing)
            limit 10
        """), {"ticker": ticker}).mappings().all()

    return {
        "ticker": ticker,
        "price_series": [dict(r) for r in prices],
        "news": [dict(r) for r in news],
        "risk_summary": [dict(r) for r in risks],
    }