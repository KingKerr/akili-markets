## RAG: 10‑K Risk Summary

This module implements a retrieval‑augmented generation (RAG) flow that
summarizes the major risks disclosed in a company’s 10‑K for a given
ticker and year.

The `year` argument refers to the filing year (from `filing_date` in
`fact_filing_section`), not the calendar year of price or news data.

### High‑level design

- **Data layer**
  - Source tables: `fact_filing_section` and `fact_risk_factor` with
    `ticker`, `form_type`, `filing_date`, `section_name`, and risk text.
  - Warehouse facts/dims are published into Postgres, including:
    - `dim_ticker`, with backfills from staged facts for late-arriving tickers.
    - `dim_date`, with backfills from staged dates so `trade_date` FKs
      in `fact_price_daily` always resolve.

- **RAG storage (`rag_chunk`)**
  - Schema:
    - `chunk_id` (UUID primary key)
    - `ticker` (FK to `dim_ticker`)
    - `doc_type` (`'10-K'` or `'risk_factor'`)
    - `doc_id` (filing or risk‑factor id)
    - `section_name`
    - `filing_date`
    - `chunk_order` (zero-based index within each doc)
    - `chunk_text`
    - `embedding vector(1536)` (OpenAI `text-embedding-3-small`)
    - `metadata jsonb`
    - `created_at`
  - Indexes:
    - `btree (ticker, doc_type, filing_date desc)` for metadata filtering
    - IVFFlat vector index on `embedding` for ANN search
  - Uniqueness:
    - `unique (ticker, doc_type, doc_id, chunk_order)` so chunk loads
      are idempotent.

### RAG pipeline

1. **Chunking & ingestion**
   - `src/rag/chunk_loader.py` loads 10‑K sections and risk‑factor text
     for each ticker/filing from Postgres.
   - `src/rag/chunking.py` splits documents into overlapping chunks,
     preserving section boundaries where possible.
   - `src/rag/embeddings.py` can be run as a CLI:
   
     ```bash
     uv run python -m src.rag.embeddings --ticker AAPL --year 2025 --limit 200
     ```
     This filters by ticker/year/doc_types, chunks the text, generates embeddings in batches, and upserts into `rag_chunk`.

2. **Retrieval**
   - `src/rag/retrieve.py`:
     - embeds the query
     - retrieves top chunks filtered by:
       - `ticker = :ticker`
       - `doc_type in ('10-K', 'risk_factor')`
       - `extract(year from filing_date) = :year` (when provided)
     - orders by cosine distance against the query embedding.

3. **Answer generation**
   - `src/rag/prompts.py` defines a `TEN_K_RISK_SUMMARY_PROMPT`
     instructing the model to:
       - group risks into themes,
       - use only retrieved evidence,
       - avoid fabricating facts.
   - `src/rag/service.py` can be run as a CLI:

     ```bash
     uv run python -m src.rag.service AAPL 2025 --show-chunks
     ```
     which which calls `summarize_ten_k_risks("AAPL", 2025)` and prints both the summary and retrieval metadata.

## How to Run

This project can be run in two ways:

1. **Quickstart** — run the RAG demo against an already-populated warehouse.
2. **Full pipeline** — rebuild the end-to-end flow from staged data through publishing and RAG.

### Quickstart

Use this path if the DuckDB staging layer and Postgres warehouse tables are already populated.

#### Prerequisites

Set the required environment variables:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL` (optional, defaults to `text-embedding-3-small`)
- `CHAT_MODEL` (optional, defaults to `gpt-4.1-mini`)

#### Steps

> Note: Replace `AAPL` and `2025` with any ticker and filing year that
> actually exist in your warehouse. For example, `NFLX 2026` or `NKE 2025`
> depending on which filings you’ve ingested.

Ingest news using ticker and date(YYYY-MM-DD):

```bash
uv run python -m src.ingest.ingest_news AAPL 2025-05-01
```
Ingest prices using stock ticker and date range:

```bash
uv run python -m src.ingest.ingest_prices AAPL 2025-01-01 2025-05-01
```
Ingest filings:

```bash
uv run python -m src.ingest.ingest_filings AAPL
```
Run your transforms for the raw data with DuckDB:

```bash
uv run python src/transforms/duckdb_stage.py
```
Publish to Postgres:

```bash
uv run python src/transforms/publish_postgres.py
```

Create the RAG schema in Postgres:

```bash
psql "$DATABASE_URL" -f sql/030_rag.sql
```

Build and load embeddings into `rag_chunk`:

```bash
uv run python -m src.rag.embeddings --ticker AAPL --year 2025
```

Run the 10-K risk summary service:

```bash
uv run python -m src.rag.service AAPL 2025 --show-chunks
```

Expected output:

- a grounded risk summary for the sample ticker/year
- a message showing the number of retrieved chunks, e.g. `Retrieved 8 chunks`

### Full pipeline

Use this path to rebuild the project end-to-end from the staging layer through the RAG service.

#### 1. Build staging tables in DuckDB

Run the staging pipeline to populate the intermediate DuckDB tables used by downstream transformations.

```bash
uv run python src/staging/build_duckdb.py
```

#### 2. Publish facts and dimensions to Postgres

Run the publisher to materialize the warehouse tables in Postgres, including the dimensions and fact tables used by the RAG layer.

```bash
uv run python src/transforms/publish_postgres.py
```

This step should populate tables such as:

- `dim_ticker`
- `fact_filing_section`
- `fact_risk_factor`
- `fact_news`
- other warehouse tables required by downstream analytics

#### 3. Create the RAG schema

Create the `rag_chunk` table, indexes, and uniqueness constraint in Postgres.

```bash
psql "$DATABASE_URL" -f sql/030_rag.sql
```

#### 4. Build chunk embeddings

Load filing sections and risk factors from Postgres, chunk the text, generate embeddings, and insert them into `rag_chunk`. You can do so like this:

```bash
uv run python -m src.rag.embeddings --ticker AAPL --year 2025 --limit 200
```

#### 5. Run the RAG service

Execute the end-to-end 10-K risk summary example:

```bash
uv run python -m src.rag.service AAPL 2025 --show-chunks
```

### Notes

- The RAG layer depends on the warehouse tables being populated first, especially:
  - `dim_ticker`
  - `fact_filing_section`
  - `fact_risk_factor`
- If `src.rag.service` returns `Retrieved 0 chunks`, confirm that:
  - `030_rag.sql` has been applied,
  - `src.rag.embeddings` has been run successfully,
  - `rag_chunk` contains rows,
  - the requested ticker/year exists in the underlying filing data.
  (i.e., `fact_filing_section` / `fact_risk_factor` contain rows with
  `ticker` and `extract(year from filing_date) = year`).
- The first embedding load may take some time depending on corpus size and API latency.

### Example

Run the sample service entry point:

```bash
uv run python -m src.rag.service AAPL 2025 --show-chunks
```

This executes:

```python
summarize_ten_k_risks("AAPL", 2025)
```

and returns:

- a natural-language summary of major 10-K risk themes
- the retrieved supporting chunks used to ground the answer