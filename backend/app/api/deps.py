"""
FastAPI dependency providers.
All heavy singletons are created once and reused across requests.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, init_db
from app.llm.openai_client import OpenAIClient
from app.crawler.httpx_crawler import HttpxCrawler
from app.crawler.portal_client import PortalClient
from app.classifier.hybrid import HybridClassifier
from app.extractor.pdf_extractor import PDFExtractor
from app.rag.vector_store import ChromaVectorStore
from app.rag.pipeline import RAGPipeline


@lru_cache(maxsize=1)
def get_llm() -> OpenAIClient:
    return OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    chroma_dir = Path(settings.data_dir) / "chroma"
    return ChromaVectorStore(persist_dir=chroma_dir)


@lru_cache(maxsize=1)
def get_rag_pipeline() -> RAGPipeline:
    return RAGPipeline(vector_store=get_vector_store(), llm_client=get_llm())


def get_db():
    """FastAPI dependency: yields a DB session per request."""
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_crawler(db: Session) -> HttpxCrawler:
    portal_client = PortalClient(
        api_base_url=f"{settings.portal_url.rstrip('/')}/api"
                     .replace("fo1.altius.finance", "fo1.api.altius.finance")
    )
    return HttpxCrawler(settings=settings, session=db, client=portal_client)


def get_classifier() -> HybridClassifier:
    return HybridClassifier(llm_client=get_llm())


def get_extractor() -> PDFExtractor:
    return PDFExtractor(llm_client=get_llm())
