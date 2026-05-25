import os
import argparse
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
    ticker = ticker.upper().strip()
    year = int(year)
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

def parse_args():
    parser = argparse.ArgumentParser(
        description = "Summarize 10-K risks for a ticker and year using RAG."
    )
    parser.add_argument(
        "ticker",
        type=str,
        help="Ticker symbol, e.g. NFL"
    )
    parser.add_argument(
        "year",
        type=int, 
        help="Filing year to retrieve, e.g. 2026"
    )
    parser.add_argument(
        "--limit",
        type=int, 
        default=8, 
        help="Maximum number of trunks to retrieve (default: 8)"
    )
    parser.add_argument(
        "--show-chunks",
        action="store_true",
        help="Print retrieved chunk metadata for debugging"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    result = summarize_ten_k_risks(
        ticker=args.ticker,
        year=args.year, 
        limit=args.limit,
    )
    if result["answer"] is None: 
        print(result.get("message", "No answer was generated."))
        print(f"Retrieved {len(result['chunks'])} chunks")
        return

    print(result["answer"])
    print(f"Retrieved {len(result['chunks'])} chunks")

    if args.show_chunks:
        for i, c in enumerate(result["chunks"], start=1):
            print(
                f"[{i}] "
                f"ticker={c.get('ticker')} | "
                f"doc_type={c.get('doc_type')} | "
                f"section_name={c.get('section_name')} | "
                f"filing_date={c.get('filing_date')} | "
                f"similarity={round(c.get('similarity', 0), 4)}"
            )

if __name__ == "__main__":
    main()