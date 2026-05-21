import os
from sqlalchemy import create_engine, text
from src.rag.chunking import chunk_text

def postgres_url():
    return (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )

def get_engine():
    return create_engine(postgres_url())

def load_filing_section_docs(conn):
    rows = conn.execute(text("""
        select
          filing_id as doc_id,
          ticker,
          form_type as doc_type,
          filing_date,
          section_name,
          section_text as doc_text
        from fact_filing_section
        where section_text is not null
          and length(section_text) > 200
          and form_type = '10-K'
          and (
            section_name ilike '%risk%'
            or section_name ilike '%item 1a%'
          )
    """)).mappings().all()
    return [dict(r) for r in rows]

def load_risk_docs(conn):
    rows = conn.execute(text("""
        select
          risk_factor_id as doc_id,
          ticker,
          'risk_factor' as doc_type,
          filing_date,
          concat_ws(' | ', category_level_1, category_level_2, category_level_3) as section_name,
          concat_ws(E'\n\n', risk_title, risk_text) as doc_text
        from fact_risk_factor
        where risk_text is not null
          and length(risk_text) > 100
    """)).mappings().all()
    return [dict(r) for r in rows]

def build_chunks():
    engine = get_engine()
    chunks = []

    with engine.begin() as conn:
        docs = load_filing_section_docs(conn) + load_risk_docs(conn)

    for doc in docs:
        piece_list = chunk_text(doc["doc_text"], chunk_size=1400, overlap=200)
        for piece in piece_list:
            chunks.append({
                "ticker": doc["ticker"],
                "doc_type": doc["doc_type"],
                "doc_id": doc["doc_id"],
                "section_name": doc["section_name"],
                "filing_date": doc["filing_date"],
                "chunk_order": piece["chunk_order"],
                "chunk_text": piece["chunk_text"],
                "metadata": {
                    "section_name": doc["section_name"],
                    "filing_date": str(doc["filing_date"]) if doc["filing_date"] else None,
                    "doc_type": doc["doc_type"]
                }
            })
    return chunks

if __name__ == "__main__":
    data = build_chunks()
    print(f"Built {len(data)} chunks")