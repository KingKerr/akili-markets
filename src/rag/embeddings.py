import os
import json
from sqlalchemy import create_engine, text
from openai import OpenAI
from src.rag.chunk_loader import build_chunks

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed_texts(client, texts, model):
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]

def upsert_chunks(engine, rows):
    with engine.begin() as conn:
        for row in rows:
            conn.execute(text("""
                insert into rag_chunk (
                  ticker, doc_type, doc_id, section_name, filing_date,
                  chunk_order, chunk_text, embedding, metadata
                )
                values (
                  :ticker, :doc_type, :doc_id, :section_name, :filing_date,
                  :chunk_order, :chunk_text, :embedding, cast(:metadata as jsonb)
                )
                on conflict do nothing
            """), {
                "ticker": row["ticker"],
                "doc_type": row["doc_type"],
                "doc_id": row["doc_id"],
                "section_name": row["section_name"],
                "filing_date": row["filing_date"],
                "chunk_order": row["chunk_order"],
                "chunk_text": row["chunk_text"],
                "embedding": row["embedding"],
                "metadata": json.dumps(row["metadata"])
            })

def main(batch_size=50):
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    client = get_client()
    engine = get_engine()

    chunks = build_chunks()

    deduped = []
    seen = set()
    for c in chunks:
        key = (c["ticker"], c["doc_type"], c["doc_id"], c["chunk_order"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    for i in range(0, len(deduped), batch_size):
        batch = deduped[i:i+batch_size]
        vectors = embed_texts(client, [r["chunk_text"] for r in batch], model)
        rows = []
        for item, vec in zip(batch, vectors):
            item["embedding"] = vec
            rows.append(item)
        upsert_chunks(engine, rows)
        print(f"Inserted batch {i} - {i + len(batch)}")

if __name__ == "__main__":
    main()