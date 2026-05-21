def chunk_text(text, chunk_size=1400, overlap=200):
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    order = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            split = text.rfind("\n\n", start, end)
            if split == -1:
                split = text.rfind(". ", start, end)
            if split != -1 and split > start + 400:
                end = split + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append({
                "chunk_order": order,
                "chunk_text": chunk
            })

        order += 1
        start = max(end - overlap, start + 1)

    return chunks
