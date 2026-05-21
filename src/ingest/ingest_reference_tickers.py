# src/ingest/ingest_reference_tickers.py
import json
import os
from src.clients.massive_client import MassiveClient

def main():
    client = MassiveClient()
    payload = client.get_reference_tickers()
    outdir = "data/raw/reference_tickers"
    os.makedirs(outdir, exist_ok=True)
    with open(f"{outdir}/reference_tickers.json", "w") as f:
        json.dump(payload, f)

    print(f"Wrote reference tickers to {outdir}/reference_tickers.json")

if __name__ == "__main__":
    main()