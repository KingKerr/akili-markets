import os
import argparse
import pandas as pd
import json
from sqlalchemy import create_engine, text
from openai import OpenAI
from src.rag.chunk_loader import build_chunks

def postgres_url():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    missing = [
        k for k, v in {
            "POSTGRES_HOST": host, 
            "POSTGRES_PORT": port, 
            "POSTGRES_DB": db, 
            "POSTGRES_USER": user,
            "POSTGRES_PASSWORD": password,
        }.items() if not v or v == "None"
    ]

    if missing:
        raise ValueError(f"Missing required Postgres env vars: {','.join(missing)}")
    
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        

def get_engine():
    return create_engine(postgres_url())

def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embedding_model():
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Build and load RAG embeddings into rag_chunk."
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Optional ticker filter, e.g. NFLX"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Optional filing year filter, e.g. 2026"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of source rows to process"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size (default: 100)"
    )
    parser.add_argument(
        "--doc-types",
        nargs="*",
        default=["10-K", "risk_factor"],
        help="Document types to embed (default: 10-K risk_factor)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many rows would be processed without embedding"
    )
    return parser.parse_args()

def load_source_chunks(engine, ticker=None, year=None, doc_types=None, limit=None) -> pd.DataFrame:
    doc_types = doc_types or ["10-K", "risk_factor"]

    sql = """
        with filing_chunks as (
            select
                ticker,
                '10-K' as doc_type,
                filing_id as doc_id,
                section_name,
                filing_date,
                section_text as chunk_text,
                jsonb_build_object(
                    'source_table', 'fact_filing_section',
                    'form_type', form_type,
                    'section_name', section_name
                ) as metadata
            from fact_filing_section
            where ticker is not null
              and section_text is not null
              and form_type = '10-K'
        ),
        risk_chunks as (
            select
                ticker,
                'risk_factor' as doc_type,
                risk_factor_id as doc_id,
                category_level_1 as section_name,
                filing_date,
                risk_text as chunk_text,
                jsonb_build_object(
                    'source_table', 'fact_risk_factor',
                    'category_level_1', category_level_1,
                    'category_level_2', category_level_2,
                    'category_level_3', category_level_3
                ) as metadata
            from fact_risk_factor
            where ticker is not null
              and risk_text is not null
        )
        select *
        from (
            select * from filing_chunks
            union all
            select * from risk_chunks
        ) s
        where (:ticker is null or ticker = :ticker)
          and (:year is null or extract(year from filing_date) = :year)
          and doc_type = any(:doc_types)
        order by ticker, filing_date, doc_type, doc_id
    """

    if limit is not None:
        sql += "\nlimit :limit"

    params = {
        "ticker": ticker,
        "year": year,
        "doc_types": doc_types,
    }
    if limit is not None:
        params["limit"] = limit

    with engine.begin() as conn:
        return pd.read_sql(text(sql), conn, params=params)

def chunk_text(text_value: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    text_value = (text_value or "").strip()
    if not text_value:
        return []

    chunks = []
    start = 0
    while start < len(text_value):
        end = start + chunk_size
        chunks.append(text_value[start:end])
        if end >= len(text_value):
            break
        start = max(end - overlap, start + 1)
    return chunks

def expand_into_chunks(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, row in df.iterrows():
        pieces = chunk_text(row["chunk_text"])
        for idx, piece in enumerate(pieces):
            rows.append({
                "ticker": row["ticker"],
                "doc_type": row["doc_type"],
                "doc_id": row["doc_id"],
                "section_name": row["section_name"],
                "filing_date": row["filing_date"],
                "chunk_order": idx,
                "chunk_text": piece,
                "metadata": row["metadata"],
            })

    return pd.DataFrame(rows)


def embed_texts(texts: list[str], batch_size: int) -> list[list[float]]:
    client = get_client()
    model = embedding_model()
    vectors = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=model,
            input=batch,
        )
        vectors.extend([item.embedding for item in response.data])

    return vectors

def upsert_rag_chunks(engine, df: pd.DataFrame) -> int:
    if df.empty:
        print("[skip] rag_chunk: no rows to upsert")
        return 0

    records = df.to_dict(orient="records")

    sql = text("""
        insert into rag_chunk (
            ticker,
            doc_type,
            doc_id,
            section_name,
            filing_date,
            chunk_order,
            chunk_text,
            metadata,
            embedding
        )
        values (
            :ticker,
            :doc_type,
            :doc_id,
            :section_name,
            :filing_date,
            :chunk_order,
            :chunk_text,
            cast(:metadata as jsonb),
            cast(:embedding as vector)
        )
        on conflict (ticker, doc_type, doc_id, chunk_order)
        do update set
            section_name = excluded.section_name,
            filing_date = excluded.filing_date,
            chunk_text = excluded.chunk_text,
            metadata = excluded.metadata,
            embedding = excluded.embedding
    """)

    with engine.begin() as conn:
        conn.execute(sql, records)

    print(f"[ok] rag_chunk: upserted {len(df)} rows")
    return len(df)

def main():
    args = parse_args()
    engine = get_engine()

    ticker = args.ticker.upper().strip() if args.ticker else None

    source_df = load_source_chunks(
        engine,
        ticker=ticker,
        year=args.year,
        doc_types=args.doc_types,
        limit=args.limit,
    )

    if source_df.empty:
        print("[skip] embeddings: no source rows found")
        return

    print(f"[ok] source rows: {len(source_df)}")

    chunk_df = expand_into_chunks(source_df)

    if chunk_df.empty:
        print("[skip] embeddings: no chunk rows produced")
        return

    print(f"[ok] chunk rows: {len(chunk_df)}")

    if args.dry_run:
        print("[dry-run] skipping embedding generation and upsert")
        return

    chunk_df["embedding"] = embed_texts(
        chunk_df["chunk_text"].tolist(),
        batch_size=args.batch_size,
    )

    chunk_df["metadata"] = chunk_df["metadata"].apply(
        lambda x: x if isinstance(x, str) else (x if x is not None else "{}")
    )
    chunk_df["metadata"] = chunk_df["metadata"].apply(
        lambda x: x if isinstance(x, str) else json.dumps(x or {})
    )
    upsert_rag_chunks(engine, chunk_df)


if __name__ == "__main__":
    main()