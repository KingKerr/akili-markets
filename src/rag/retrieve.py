import os
from sqlalchemy import create_engine, text
from openai import OpenAI

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed_query(query):
    client = get_client()
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    result = client.embeddings.create(model=model, input=[query])
    return result.data[0].embedding

def retrieve_chunks(ticker, query, year=None, doc_types=None, limit=6):
    doc_types = doc_types or ["10-K", "risk_factor"]
    query_embedding = embed_query(query)
    engine = get_engine()

    sql = text("""
        select
          ticker,
          doc_type,
          doc_id,
          section_name,
          filing_date,
          chunk_text,
          metadata,
          1 - (embedding <=> cast(:query_embedding as vector)) as similarity
        from rag_chunk
        where ticker = :ticker
          and doc_type = any(:doc_types)
          and (:year is null or extract(year from filing_date) = :year)
        order by embedding <=> cast(:query_embedding as vector)
        limit :limit
    """)

    with engine.begin() as conn:
        rows = conn.execute(sql, {
            "ticker": ticker,
            "doc_types": doc_types,
            "query_embedding": str(query_embedding),
            "year": year,
            "limit": limit
        }).mappings().all()

    return [dict(r) for r in rows]