"""
PDF chunker: one chunk per page, skipping near-empty pages and cover pages.

Page-level chunks work well for financial reports:
- Each page is largely self-contained (one topic / one table).
- Retrieval of a full page gives the LLM enough context to quote accurately.
- Chunks are small enough to fit many into a single prompt.

Cover/title pages are excluded because they consist almost entirely of short
label lines (fund name, reporting period, GP name) with no analytical content.
Including them causes retrieval for broad synthesis queries (e.g. "strategy
shift 2022–2025") to surface these label-heavy pages instead of commentary pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF — fastest page-text extraction


MIN_CHUNK_CHARS = 60    # skip near-empty pages
_COVER_MAX_LINES = 30   # cover pages are short
_COVER_SHORT_LINE_LEN = 50   # a line this short is considered a "label"
_COVER_SHORT_LINE_RATIO = 0.72  # if >= this fraction are label lines, it's a cover


@dataclass
class Chunk:
    id: str            # globally unique; used for ChromaDB upsert idempotency
    text: str
    metadata: dict     # file_id, filename, fund_name, doc_type, page, period


def _is_cover_page(text: str) -> bool:
    """
    Return True when a page looks like a cover/title page with no analytical prose.

    Heuristic: a page is a cover page when it has few lines AND the overwhelming
    majority of those lines are short label fragments (fund name, date, GP name,
    section header).  A page that contains even a short paragraph of commentary
    will have enough long lines to fall below the threshold.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    if len(lines) > _COVER_MAX_LINES:
        return False
    short_count = sum(1 for ln in lines if len(ln) < _COVER_SHORT_LINE_LEN)
    return (short_count / len(lines)) >= _COVER_SHORT_LINE_RATIO


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
        if _is_cover_page(text):
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
