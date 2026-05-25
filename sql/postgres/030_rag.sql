create table if not exists rag_chunk (
  chunk_id uuid primary key default gen_random_uuid(),
  ticker text not null references dim_ticker(ticker),
  doc_type text not null,
  doc_id text not null,
  section_name text,
  filing_date date,
  chunk_order int not null,
  chunk_index integer not null,
  chunk_text text not null,
  embedding vector(1536) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz default now()
);

create unique index if not exists idx_rag_ticker_doc_type
  on rag_chunk (ticker, doc_type, filing_date desc);

create index if not exists idx_rag_embedding
  on rag_chunk using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'rag_chunk_unique_doc_chunk'
  ) then
    alter table rag_chunk
    add constraint rag_chunk_unique_doc_chunk
    unique (ticker, doc_type, doc_id, chunk_order);
  end if;
end $$;
