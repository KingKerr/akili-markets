import os
import json
from sqlalchemy import create_engine, text
from openai import OpenAI
from src.rag.retrieve import retrieve_chunks

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_latest_metrics(conn, ticker):
    row = conn.execute(text("""
        select
          ticker,
          trade_date,
          close,
          return_1d,
          return_5d,
          volatility_20d,
          volume_vs_20d,
          gap_from_prev_close
        from fact_price_daily
        where ticker = :ticker
        order by trade_date desc
        limit 1
    """), {"ticker": ticker}).mappings().first()
    return dict(row) if row else {}

def normalize_chunk(chunk):
    return {
        "doc_type": chunk["doc_type"],
        "doc_id": chunk["doc_id"],
        "section_name": chunk["section_name"],
        "filing_date": str(chunk["filing_date"]) if chunk["filing_date"] else None,
        "similarity": float(chunk["similarity"]) if chunk.get("similarity") is not None else None,
        "chunk_text": chunk["chunk_text"][:900]
    }

def compose_compare_prompt(ticker_a, ticker_b, metrics_a, metrics_b, chunks_a, chunks_b, question):
    return f"""
You are a grounded market intelligence assistant.

Compare {ticker_a} and {ticker_b} using ONLY the supplied evidence.
Focus on:
1. Shared themes
2. Key differences
3. What appears more material for one company than the other
4. Explicit uncertainty

Question:
{question}

Metrics for {ticker_a}:
{json.dumps(metrics_a, default=str)}

Metrics for {ticker_b}:
{json.dumps(metrics_b, default=str)}

Retrieved evidence for {ticker_a}:
{json.dumps(chunks_a, default=str)}

Retrieved evidence for {ticker_b}:
{json.dumps(chunks_b, default=str)}

Return strict JSON:
{{
  "answer": "short comparison paragraph",
  "shared_themes": ["..."],
  "differences": ["..."],
  "caveats": ["..."]
}}
"""

def compare_answer(ticker_a, ticker_b, question):
    engine = get_engine()
    client = get_client()

    with engine.begin() as conn:
        metrics_a = get_latest_metrics(conn, ticker_a)
        metrics_b = get_latest_metrics(conn, ticker_b)

    chunks_a = [normalize_chunk(c) for c in retrieve_chunks(ticker_a, question, ["10-K", "risk_factor"], 5)]
    chunks_b = [normalize_chunk(c) for c in retrieve_chunks(ticker_b, question, ["10-K", "risk_factor"], 5)]

    prompt = compose_compare_prompt(ticker_a, ticker_b, metrics_a, metrics_b, chunks_a, chunks_b, question)

    response = client.responses.create(
        model=os.getenv("CHAT_MODEL", "gpt-4.1-mini"),
        input=prompt
    )

    text_out = response.output_text
    try:
        parsed = json.loads(text_out)
    except Exception:
        parsed = {
            "answer": text_out,
            "shared_themes": [],
            "differences": [],
            "caveats": ["Model output was not valid JSON."]
        }

    return {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "chunks_a": chunks_a,
        "chunks_b": chunks_b,
        "response": parsed
    }