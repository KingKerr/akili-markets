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

def get_price_context(conn, ticker):
    row = conn.execute(text("""
        select
          ticker,
          trade_date,
          close,
          return_1d,
          return_5d,
          volume,
          volume_vs_20d,
          volatility_20d,
          gap_from_prev_close
        from fact_price_daily
        where ticker = :ticker
        order by trade_date desc
        limit 1
    """), {"ticker": ticker}).mappings().first()
    return dict(row) if row else {}

def get_recent_news(conn, ticker, limit=5):
    rows = conn.execute(text("""
        select
          published_at,
          title,
          summary,
          article_url
        from fact_news
        where ticker = :ticker
        order by published_at desc
        limit :limit
    """), {"ticker": ticker, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]

def normalize_chunk(chunk):
    return {
        "doc_type": chunk["doc_type"],
        "doc_id": chunk["doc_id"],
        "section_name": chunk["section_name"],
        "filing_date": str(chunk["filing_date"]) if chunk["filing_date"] else None,
        "similarity": float(chunk["similarity"]) if chunk.get("similarity") is not None else None,
        "chunk_text": chunk["chunk_text"][:1200]
    }

def compose_prompt(ticker, question, price_ctx, news_ctx, retrieved_chunks):
    return f"""
You are a grounded market intelligence assistant.

Answer the user's question about {ticker} using ONLY the supplied data.
Prefer structured metrics for price behavior and use retrieved text for explanatory evidence.
If the evidence is incomplete, explicitly say what is missing.

Question:
{question}

Structured metrics:
{json.dumps(price_ctx, default=str)}

Recent news:
{json.dumps(news_ctx, default=str)}

Retrieved filing/risk evidence:
{json.dumps(retrieved_chunks, default=str)}

Return strict JSON with this schema:
{{
  "answer": "short paragraph",
  "evidence_bullets": ["bullet 1", "bullet 2"],
  "caveats": ["caveat 1"],
  "used_doc_types": ["10-K", "risk_factor"]
}}
"""

def answer_question(ticker, question):
    engine = get_engine()
    client = get_client()

    with engine.begin() as conn:
        price_ctx = get_price_context(conn, ticker)
        news_ctx = get_recent_news(conn, ticker)

    raw_chunks = retrieve_chunks(ticker, question, doc_types=["10-K", "risk_factor"], limit=6)
    retrieved_chunks = [normalize_chunk(c) for c in raw_chunks]

    prompt = compose_prompt(ticker, question, price_ctx, news_ctx, retrieved_chunks)

    response = client.responses.create(
        model=os.getenv("CHAT_MODEL", "gpt-4.1-mini"),
        input=prompt
    )

    output_text = response.output_text

    try:
        parsed = json.loads(output_text)
    except Exception:
        parsed = {
            "answer": output_text,
            "evidence_bullets": [],
            "caveats": ["Model output was not valid JSON."],
            "used_doc_types": list({c["doc_type"] for c in retrieved_chunks})
        }

    return {
        "ticker": ticker,
        "question": question,
        "metrics": price_ctx,
        "recent_news": news_ctx,
        "retrieved_chunks": retrieved_chunks,
        "response": parsed
    }