import json
import os
import sys
from src.clients.massive_client import MassiveClient


def main(ticker, from_date, to_date, multiplier=1, timespan="day"):
    client = MassiveClient()
    payload = client.get_aggs(ticker, multiplier, timespan, from_date, to_date)
    outdir = f"data/raw/aggs_ticker/ticker={ticker}"
    os.makedirs(outdir, exist_ok=True)
    with open(f"{outdir}/{from_date}_{to_date}.json", "w") as f:
        json.dump(payload, f)

if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])