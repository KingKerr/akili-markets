import os
import requests

BASE_URL = "https://api.massive.com"

class MassiveClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("MASSIVE_API_KEY")
        self.base_url = BASE_URL
        self.session = requests.Session()

    def _get(self, path, params=None):
        params = params or {}
        params["apiKey"] = self.api_key
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def get_tickers(self, limit=1000, active="true"):
        return self._get("/v3/reference/tickers", {"limit": limit, "active": active})

    def get_ticker_overview(self, ticker):
        return self._get(f"/v3/reference/tickers/{ticker}")
    
    def get_reference_tickers(self, market="stocks", active=True, limit=1000):
        url = f"{self.base_url}/v3/reference/tickers"
        params = {
            "market": market,
            "active": str(active).lower(),
            "limit": limit,
            "apiKey": self.api_key,
            }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_grouped_daily(self, date_str):
        return self._get(f"/v2/aggs/grouped/locale/us/market/stocks/{date_str}")

    def get_aggs(self, ticker, multiplier, timespan, from_date, to_date):
        return self._get(
            f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        )

    def get_news(self, ticker=None, published_utc_gte=None, limit=100):
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if published_utc_gte:
            params["published_utc.gte"] = published_utc_gte
        return self._get("/v2/reference/news", params)

    def get_related_companies(self, ticker):
        return self._get(f"/v1/related-companies/{ticker}")

    def get_10k_sections(self, ticker, limit=10):
        return self._get("/stocks/filings/10-K/vX/sections", {"ticker": ticker, "limit": limit})

    def get_risk_factors(self, ticker, limit=100):
        return self._get("/stocks/filings/vX/risk-factors", {"ticker": ticker, "limit": limit})