import json
import os
from datetime import date
from src.clients.massive_client import MassiveClient

def main():
    client = MassiveClient()
    payload = client.get_tickers(limit=1000, active="true")
    load_date = date.today().isoformat()
    outdir = f"data/raw/reference_tickers/load_date={load_date}"
    os.makedirs(outdir, exist_ok=True)
    with open(f"{outdir}/tickers.json", "w") as f:
        json.dump(payload, f)

if __name__ == "__main__":
    main()