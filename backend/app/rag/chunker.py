"""
PDF chunker: one chunk per page, skipping near-empty pages.

Page-level chunks work well for financial reports:
- Each page is largely self-contained (one topic / one table).
- Retrieval of a full page gives the LLM enough context to quote accurately.
- Chunks are small enough to fit many into a single prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF — fastest page-text extraction


MIN_CHUNK_CHARS = 60   # skip pages with less useful content than this


@dataclass
class Chunk:
    id: str            # globally unique; used for ChromaDB upsert idempotency
    text: str
    metadata: dict     # file_id, filename, fund_name, doc_type, page, period


def chunk_pdf(file_path: Path, metadata: dict) -> list[Chunk]:
    """
    Split a PDF into one Chunk per page.
    *metadata* must contain at least {"file_id": int, "filename": str}.
    Any extra keys (fund_name, doc_type, period, etc.) are forwarded to ChromaDB.
    """
    file_id = metadata["file_id"]
    chunks: list[Chunk] = []

    try:
        doc = fitz.open(str(file_path))
    except Exception as exc:
        raise ValueError(f"Cannot open {file_path.name}: {exc}") from exc

    for page_num, page in enumerate(doc):
        text = page.get_text().strip()
        if len(text) < MIN_CHUNK_CHARS:
            continue
        chunks.append(
            Chunk(
                id=f"file{file_id}_p{page_num + 1}",
                text=text,
                metadata={
                    **{k: str(v) if v is not None else "" for k, v in metadata.items()},
                    "page": str(page_num + 1),
                },
            )
        )

    doc.close()
    return chunks
