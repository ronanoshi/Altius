from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Citation:
    filename: str
    file_path: str
    page: int
    chunk_text: str
    fund_name: str | None = None
    period: str | None = None      # e.g. "Q3 2025" or "2025-09-30"


@dataclass
class RAGResponse:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    is_out_of_corpus: bool = False  # True when question cannot be grounded in docs


class BaseRAG(ABC):
    @abstractmethod
    async def ingest(self, file_path: Path, metadata: dict) -> int:
        """
        Chunk and embed a document.
        Idempotent — re-ingesting the same file_id is a no-op.
        Returns the number of NEW chunks added.
        """
        ...

    @abstractmethod
    async def query(self, question: str, n_results: int = 8) -> RAGResponse:
        """
        Answer a natural-language question using retrieved document chunks.
        Every claim in the answer must be traceable to a Citation.
        Out-of-corpus questions are answered honestly (is_out_of_corpus=True).
        """
        ...
