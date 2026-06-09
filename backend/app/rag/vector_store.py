"""
ChromaDB wrapper with upsert-based idempotency.

Uses ChromaDB's built-in ONNX embedding model (all-MiniLM-L6-v2) —
no OpenAI key needed for ingestion or retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from .chunker import Chunk


@dataclass
class RetrievedChunk:
    id: str
    text: str
    metadata: dict
    distance: float   # cosine distance; lower = more similar


# Distance threshold above which we consider a question out-of-corpus
OUT_OF_CORPUS_DISTANCE = 0.75


class ChromaVectorStore:
    def __init__(self, persist_dir: str | Path):
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        # Default local embedding — no API key required
        self._ef = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name="documents",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """
        Upsert chunks into the collection.
        Chunks whose ID already exists are silently skipped (idempotent).
        Returns the number of genuinely new chunks added.
        """
        if not chunks:
            return 0

        existing_ids = set(
            self._collection.get(ids=[c.id for c in chunks])["ids"]
        )
        new_chunks = [c for c in chunks if c.id not in existing_ids]

        if new_chunks:
            self._collection.add(
                ids=[c.id for c in new_chunks],
                documents=[c.text for c in new_chunks],
                metadatas=[c.metadata for c in new_chunks],
            )

        return len(new_chunks)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def query(self, text: str, n_results: int = 8) -> list[RetrievedChunk]:
        """Return the n_results most relevant chunks for *text*."""
        n_results = min(n_results, max(1, self._collection.count()))
        results = self._collection.query(
            query_texts=[text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        chunks: list[RetrievedChunk] = []
        for cid, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(RetrievedChunk(id=cid, text=doc, metadata=meta, distance=dist))
        return chunks

    def query_in_filenames(self, text: str, filenames: list[str], n_results: int = 4) -> list[RetrievedChunk]:
        """
        Semantic query restricted to a specific set of filenames.
        Used for year-targeted supplemental retrieval.
        """
        count = self._collection.count()
        if count == 0 or not filenames:
            return []
        # ChromaDB $in filter on filename metadata
        try:
            n_results = min(n_results, count)
            results = self._collection.query(
                query_texts=[text],
                n_results=n_results,
                where={"filename": {"$in": filenames}},
                include=["documents", "metadatas", "distances"],
            )
            chunks: list[RetrievedChunk] = []
            for cid, doc, meta, dist in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                chunks.append(RetrievedChunk(id=cid, text=doc, metadata=meta, distance=dist))
            return chunks
        except Exception:
            return []

    def is_out_of_corpus(self, chunks: list[RetrievedChunk]) -> bool:
        """True if the best match is too distant to be a real answer."""
        return not chunks or chunks[0].distance > OUT_OF_CORPUS_DISTANCE

    def count(self) -> int:
        return self._collection.count()
