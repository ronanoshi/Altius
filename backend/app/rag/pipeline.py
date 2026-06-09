"""
RAGPipeline: ingest + query orchestration.

Ingestion uses local ChromaDB embeddings (no API key).
Query answer generation uses the injected LLM client (GPT-4o by default).
"""
from __future__ import annotations

from pathlib import Path

from app.llm.base import BaseLLMClient
from .base import BaseRAG, Citation, RAGResponse
from .chunker import chunk_pdf
from .vector_store import ChromaVectorStore


_CHAT_SYSTEM = """\
You are a financial analyst assistant for a private equity family office.
Answer the question using ONLY the document excerpts provided below.
Rules:
- Cite every factual claim with [filename, page N, period P].
- For cross-quarter synthesis, cite each relevant period separately.
- If the answer is not present in the excerpts, say exactly:
  "This information is not available in the provided documents."
- Never fabricate data, fund names, dates, or figures.\
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
        label = (
            f"[{meta.get('filename', '?')}, "
            f"page {meta.get('page', '?')}, "
            f"period {meta.get('period', 'unknown')}]"
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

    async def query(self, question: str, n_results: int = 8) -> RAGResponse:
        retrieved = self._store.query(question, n_results=n_results)

        if self._store.is_out_of_corpus(retrieved):
            return RAGResponse(
                answer="This information is not available in the provided documents.",
                citations=[],
                is_out_of_corpus=True,
            )

        context = _format_context(retrieved)

        if self._llm is None:
            # No LLM configured — return raw retrieved chunks as the "answer"
            return RAGResponse(
                answer="[LLM not configured — retrieved chunks shown below]\n\n" + context,
                citations=_to_citations(retrieved),
                is_out_of_corpus=False,
            )

        answer = await self._llm.chat(
            system=_CHAT_SYSTEM,
            user=_CHAT_USER_TMPL.format(question=question, context=context),
        )

        return RAGResponse(
            answer=answer,
            citations=_to_citations(retrieved),
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
