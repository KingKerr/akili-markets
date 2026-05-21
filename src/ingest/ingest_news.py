import json
import os
from datetime import datetime, timedelta, UTC
from src.clients.massive_client import MassiveClient

def main(ticker):
    client = MassiveClient()
    since = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
    print(f"Fetching news for {ticker} since {since}")
    payload = client.get_news(ticker=ticker, published_utc_gte=since, limit=100)
    outdir = f"data/raw/news/ticker={ticker}"
    os.makedirs(outdir, exist_ok=True)
    with open(f"{outdir}/news.json", "w") as f:
        json.dump(payload, f)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])