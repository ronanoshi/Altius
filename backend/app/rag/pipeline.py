"""
RAGPipeline: ingest + query orchestration.

Ingestion uses local ChromaDB embeddings (no API key).
Query answer generation uses the injected LLM client (GPT-4o by default).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.llm.base import BaseLLMClient
from .base import BaseRAG, Citation, RAGResponse
from .chunker import chunk_pdf
from .vector_store import ChromaVectorStore


_YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Period extraction from filename so the LLM knows which reporting period a
# chunk belongs to even when the metadata "period" field was not populated.
_DATE_RE   = re.compile(r"(\d{4})-(\d{2})-\d{2}")   # YYYY-MM-DD  → Q? YYYY
_QN_RE     = re.compile(r"[Qq]([1-4])[\W_](\d{4})")  # q3_2022 / Q1-2025
_MONTH_RE  = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(\d{4})", re.I)
_MONTH_TO_Q = {1:1,2:1,3:1,4:2,5:2,6:2,7:3,8:3,9:3,10:4,11:4,12:4}
_MONTH_NUM  = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
               "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}


def _period_from_filename(filename: str) -> str:
    """Best-effort period label extracted from the filename."""
    # 2025-03-31  →  Q1 2025
    m = _DATE_RE.search(filename)
    if m:
        q = _MONTH_TO_Q[int(m.group(2))]
        return f"Q{q} {m.group(1)}"
    # q3_2022 / Q1_2025
    m = _QN_RE.search(filename)
    if m:
        return f"Q{m.group(1)} {m.group(2)}"
    # Jun2023 / Dec2024
    m = _MONTH_RE.search(filename)
    if m:
        q = _MONTH_TO_Q[_MONTH_NUM[m.group(1).lower()]]
        return f"Q{q} {m.group(2)}"
    return "unknown"


_CHAT_SYSTEM = """\
You are a financial analyst assistant for a private equity family office.
Answer the question using ONLY the document excerpts provided below.
Rules:
- Cite every factual claim with [filename, page N, period P].
- For cross-quarter synthesis, cite each relevant period separately.
- If the answer is not present in the excerpts, say exactly:
  "This information is not available in the provided documents."
- Never fabricate data, fund names, dates, or figures.
- Treat "subscription credit facility", "capital call facility", and "subscription line"
  as equivalent terms when interpreting excerpts.\
"""

_CHAT_USER_TMPL = """\
Question: {question}

Document excerpts:
{context}

Answer with citations:\
"""


def _format_context(chunks) -> str:
    parts = []
    for chunk in chunks:
        meta = chunk.metadata
        period = meta.get("period") or _period_from_filename(meta.get("filename", ""))
        label = (
            f"[{meta.get('filename', '?')}, "
            f"page {meta.get('page', '?')}, "
            f"period {period}]"
        )
        parts.append(f"{label}\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


class RAGPipeline(BaseRAG):
    def __init__(self, vector_store: ChromaVectorStore, llm_client: BaseLLMClient | None = None):
        self._store = vector_store
        self._llm = llm_client

    async def ingest(self, file_path: Path, metadata: dict) -> int:
        chunks = chunk_pdf(file_path, metadata)
        return self._store.add_chunks(chunks)

    # Retrieve a base pool via semantic search, then supplement with a focused
    # year-targeted query when the user asks about a specific year.  The year
    # query is a proper semantic search restricted to that year's documents so
    # we get the most relevant pages rather than flooding the context with noise.
    _CANDIDATE_N = 8
    _YEAR_SUPPLEMENT_N = 8   # top-N from the year-filtered secondary query
    _MAX_CONTEXT_DISTANCE = 0.70          # semantic search results
    _MAX_YEAR_SUPPLEMENT_DISTANCE = 0.76  # year-targeted results (slightly more permissive)

    async def query(self, question: str, n_results: int = _CANDIDATE_N) -> RAGResponse:
        retrieved = self._store.query(question, n_results=n_results)

        if self._store.is_out_of_corpus(retrieved):
            return RAGResponse(
                answer="This information is not available in the provided documents.",
                citations=[],
                is_out_of_corpus=True,
            )

        # Year-based supplementation: do a second query restricted to filenames
        # from each year mentioned in the question.  This is a targeted semantic
        # search so only the most relevant pages from those years are added.
        # Year-supplement chunks use a looser distance cap because they are already
        # pre-filtered to the right time period, so slightly lower similarity is OK.
        year_supplement_ids: set[str] = set()
        years = _YEAR_RE.findall(question)
        if years:
            seen_ids = {c.id for c in retrieved}
            # Collect filenames that contain the mentioned year(s)
            all_meta = self._store._collection.get(include=["metadatas"])
            year_filenames: list[str] = []
            for meta in all_meta["metadatas"]:
                fn = meta.get("filename", "")
                if any(yr in fn for yr in years) and fn not in year_filenames:
                    year_filenames.append(fn)
            if year_filenames:
                year_hits = self._store.query_in_filenames(
                    question, year_filenames, n_results=self._YEAR_SUPPLEMENT_N
                )
                for chunk in year_hits:
                    if chunk.id not in seen_ids:
                        retrieved.append(chunk)
                        year_supplement_ids.add(chunk.id)
                        seen_ids.add(chunk.id)

        # Apply distance filter:
        # - semantic hits: use _MAX_CONTEXT_DISTANCE
        # - year-supplement hits: use the more permissive _MAX_YEAR_SUPPLEMENT_DISTANCE
        filtered = [
            c for c in retrieved
            if c.distance <= (
                self._MAX_YEAR_SUPPLEMENT_DISTANCE
                if c.id in year_supplement_ids
                else self._MAX_CONTEXT_DISTANCE
            )
        ]
        if len(filtered) < 3:
            filtered = retrieved[:3]

        context = _format_context(filtered)

        if self._llm is None:
            return RAGResponse(
                answer="[LLM not configured — retrieved chunks shown below]\n\n" + context,
                citations=_to_citations(filtered),
                is_out_of_corpus=False,
            )

        answer = await self._llm.chat(
            system=_CHAT_SYSTEM,
            user=_CHAT_USER_TMPL.format(question=question, context=context),
        )

        return RAGResponse(
            answer=answer,
            citations=_to_citations(filtered),
            is_out_of_corpus=False,
        )


def _to_citations(chunks) -> list[Citation]:
    return [
        Citation(
            filename=c.metadata.get("filename", ""),
            file_path=c.metadata.get("file_path", ""),
            page=int(c.metadata.get("page", 0)),
            chunk_text=c.text[:300],
            fund_name=c.metadata.get("fund_name") or None,
            period=c.metadata.get("period") or None,
        )
        for c in chunks
    ]
