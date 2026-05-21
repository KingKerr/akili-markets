import json
import os
from src.clients.massive_client import MassiveClient

def write_payload(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f)

def main(ticker):
    client = MassiveClient()
    sections = client.get_10k_sections(ticker)
    risks = client.get_risk_factors(ticker)
    write_payload(f"data/raw/filings_10k_sections/ticker={ticker}/sections.json", sections)
    write_payload(f"data/raw/risk_factors/ticker={ticker}/risk_factors.json", risks)

if __name__ == "__main__":
    import sys
    main(sys.argv[1])