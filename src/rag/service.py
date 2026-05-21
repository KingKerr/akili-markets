import os
from openai import OpenAI
from src.rag.retrieve import retrieve_chunks
from src.rag.prompts import TEN_K_RISK_SUMMARY_PROMPT

def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def build_context(chunks):
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(
            f"[Chunk {i}]\n"
            f"ticker: {c['ticker']}\n"
            f"doc_type: {c['doc_type']}\n"
            f"section_name: {c.get('section_name')}\n"
            f"filing_date: {c.get('filing_date')}\n"
            f"similarity: {round(c.get('similarity', 0), 4)}\n"
            f"text:\n{c['chunk_text']}\n"
        )
    return "\n---\n".join(parts)

def summarize_ten_k_risks(ticker: str, year: int, limit: int = 8):
    query = f"Summarize the main risks disclosed by {ticker} in its {year} 10-K risk factors."
    chunks = retrieve_chunks(
        ticker=ticker,
        query=query,
        year=year,
        doc_types=["10-K", "risk_factor"],
        limit=limit,
    )

    if not chunks:
        return {
            "ticker": ticker,
            "year": year,
            "answer": None,
            "chunks": [],
            "message": "No relevant chunks found."
        }

    context = build_context(chunks)

    user_prompt = f"""
Ticker: {ticker}
Year: {year}
Question: Summarize the major risks disclosed in the 10-K for this year.

Retrieved evidence:
{context}
"""

    client = get_client()
    model = os.getenv("CHAT_MODEL", "gpt-4.1-mini")

    response = client.responses.create(
        model=model,
        instructions=TEN_K_RISK_SUMMARY_PROMPT,
        input=user_prompt,
    )

    answer = response.output_text

    return {
        "ticker": ticker,
        "year": year,
        "answer": answer,
        "chunks": chunks,
    }

if __name__ == "__main__":
    result = summarize_ten_k_risks("AAPL", 2024)
    print(result["answer"])
    print(f"Retrieved {len(result['chunks'])} chunks")