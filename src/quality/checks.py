from sqlalchemy import create_engine, text
import os
import json

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

CHECKS = {
    "null_ticker_price": """
        select count(*) as failing_rows
        from fact_price_daily
        where ticker is null
    """,
    "duplicate_price_pk": """
        select count(*) as failing_rows
        from (
          select ticker, trade_date, count(*) as c
          from fact_price_daily
          group by 1,2
          having count(*) > 1
        ) t
    """,
    "bad_ohlc_range": """
        select count(*) as failing_rows
        from fact_price_daily
        where low > high
           or open < low or open > high
           or close < low or close > high
    """
}

def main():
    engine = create_engine(postgres_url())
    with engine.begin() as conn:
        for check_name, sql in CHECKS.items():
            failing_rows = conn.execute(text(sql)).scalar()
            status = "pass" if failing_rows == 0 else "fail"
            conn.execute(text("""
                insert into data_quality_result (check_name, status, failing_rows, details)
                values (:check_name, :status, :failing_rows, :details)
            """), {
                "check_name": check_name,
                "status": status,
                "failing_rows": failing_rows,
                "details": json.dumps({})
            })

if __name__ == "__main__":
    main()