"""
RAG pipeline tests.

Unit tests use in-memory ChromaDB and mock LLM.
Integration test ingests real portal files (no LLM key needed for ingest).
Full chat integration test requires an OpenAI API key.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.llm.base import BaseLLMClient
from app.rag import RAGPipeline, ChromaVectorStore, RAGResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return ChromaVectorStore(persist_dir=tmp_path / "chroma")


@pytest.fixture
def pipeline(store):
    return RAGPipeline(vector_store=store)


def _write_pdf(path: Path, *pages: str) -> None:
    import fitz
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 100), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def _mock_llm(answer: str) -> BaseLLMClient:
    llm = MagicMock(spec=BaseLLMClient)
    llm.chat = AsyncMock(return_value=answer)
    return llm


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_cover_page_detection():
    """Cover/title pages are detected and content pages are not."""
    from app.rag.chunker import _is_cover_page

    cover = "\n".join([
        "Fund Alpha, L.P.",
        "Quarterly Investor Update",
        "Volume 1 — Portfolio Review",
        "REPORTING PERIOD",
        "Q3 2021 — Quarter ended September 30, 2021",
        "PREPARED FOR",
        "Evergreen Family Office LP",
        "GENERAL PARTNER",
        "Alpha Capital Management",
        "ASSET CLASS",
        "Alternatives / Private Equity",
    ])
    assert _is_cover_page(cover) is True

    content = "\n".join([
        "Portfolio Performance",
        "During the quarter the fund experienced meaningful valuation improvements.",
        "Three portfolio companies reported EBITDA growth in excess of 20% year-over-year.",
        "One position was marked down following a revenue shortfall in the consumer segment.",
        "The manager notes that elevated interest rates continue to pressure leveraged buyout returns.",
        "Subscription credit facility utilization averaged 45% over the quarter, down from 60% in Q2.",
        "The GP does not anticipate further drawdowns before year-end based on current deployment pace.",
    ])
    assert _is_cover_page(content) is False


@pytest.mark.asyncio
async def test_cover_pages_excluded_from_chunks(tmp_path):
    """A PDF whose first page is a cover and second is content yields only 1 chunk."""
    from app.rag.chunker import chunk_pdf

    cover_text = "\n".join([
        "Fund Alpha, L.P.",
        "Quarterly Investor Update",
        "REPORTING PERIOD",
        "Q3 2021",
        "PREPARED FOR",
        "Evergreen Family Office LP",
        "GENERAL PARTNER",
        "Alpha Capital Management",
    ])
    content_text = (
        "During the quarter three portfolio companies reported strong EBITDA growth. "
        "The subscription credit facility was utilised at an average rate of 45%, "
        "down from 60% in the prior quarter. One position was marked down after a "
        "revenue shortfall in the consumer segment impacted projected returns."
    )

    import fitz
    pdf = tmp_path / "mixed.pdf"
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 100), cover_text, fontsize=10)
    p2 = doc.new_page()
    p2.insert_text((50, 100), content_text, fontsize=10)
    doc.save(str(pdf))
    doc.close()

    chunks = chunk_pdf(pdf, {"file_id": 99, "filename": "mixed.pdf"})
    assert len(chunks) == 1, f"Expected 1 content chunk, got {len(chunks)}"
    assert chunks[0].metadata["page"] == "2"


@pytest.mark.asyncio
async def test_ingest_adds_chunks(pipeline, tmp_path):
    """A PDF is chunked by page and stored in ChromaDB."""
    pdf = tmp_path / "report.pdf"
    _write_pdf(
        pdf,
        "Fund Alpha LP - Quarterly Report Q3 2024. Portfolio performance was strong driven by valuation increases.",
        "Portfolio update page 2. Contributions totalled $5M and distributions were $1.2M during the period.",
    )

    added = await pipeline.ingest(pdf, {"file_id": 1, "filename": "report.pdf"})
    assert added == 2
    assert pipeline._store.count() == 2


@pytest.mark.asyncio
async def test_ingest_is_idempotent(pipeline, tmp_path):
    """Re-ingesting the same file adds zero new chunks."""
    pdf = tmp_path / "report.pdf"
    _write_pdf(pdf, "Some quarterly fund report content with enough text to pass the minimum.")

    await pipeline.ingest(pdf, {"file_id": 42, "filename": "report.pdf"})
    added_second = await pipeline.ingest(pdf, {"file_id": 42, "filename": "report.pdf"})
    assert added_second == 0


@pytest.mark.asyncio
async def test_query_returns_answer_with_citations(tmp_path):
    """Retrieved chunks are forwarded to LLM and citations are populated."""
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    llm = _mock_llm("The fund had strong performance in Q3 2024. [report.pdf, page 1, period Q3 2024]")
    pipe = RAGPipeline(vector_store=store, llm_client=llm)

    pdf = tmp_path / "report.pdf"
    _write_pdf(pdf, "Fund Alpha Q3 2024 quarterly report. Strong performance driven by portfolio companies.")
    await pipe.ingest(pdf, {"file_id": 1, "filename": "report.pdf", "period": "Q3 2024"})

    response = await pipe.query("How did the fund perform in Q3 2024?")

    assert isinstance(response, RAGResponse)
    assert "strong performance" in response.answer.lower()
    assert len(response.citations) >= 1
    assert response.is_out_of_corpus is False
    llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_query_out_of_corpus(tmp_path):
    """A question with no relevant documents is flagged as out-of-corpus."""
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    llm = _mock_llm("irrelevant answer")
    pipe = RAGPipeline(vector_store=store, llm_client=llm)

    # Ingest a financial document
    pdf = tmp_path / "report.pdf"
    _write_pdf(
        pdf,
        "Fund Alpha LP Q3 2024 quarterly report. Portfolio performance was strong. "
        "Contributions and distributions were in line with expectations.",
    )
    await pipe.ingest(pdf, {"file_id": 1, "filename": "report.pdf"})

    # Ask about something with zero semantic overlap to a PE fund report
    response = await pipe.query("What are the best pasta recipes for a dinner party?")

    assert response.is_out_of_corpus is True
    assert "not available" in response.answer.lower()
    llm.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Integration test — ingest real portal files (no LLM key needed)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_ingest_portal_files(tmp_path):
    """Download and ingest all 40 portal files into ChromaDB. No LLM required."""
    from app.config import settings
    from app.crawler.portal_client import PortalClient

    client = PortalClient(api_base_url="https://fo1.api.altius.finance/api")
    token = await client.login(settings.portal_username, settings.portal_password)
    files = await client.list_files(token, 10495)

    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    pipe = RAGPipeline(vector_store=store)

    total_chunks = 0
    for file_meta in files:
        dest = tmp_path / f"{file_meta['id']}_{file_meta['name']}"
        await client.download_file(file_meta["file_url"], dest)
        meta = {
            "file_id": file_meta["id"],
            "filename": file_meta["name"],
            "doc_type": file_meta.get("document_type", ""),
            "file_path": str(dest),
        }
        try:
            added = await pipe.ingest(dest, meta)
            total_chunks += added
            print(f"  {file_meta['name']}: {added} chunks")
        except ValueError as exc:
            print(f"  {file_meta['name']}: SKIPPED — {exc}")

    print(f"\nTotal chunks: {total_chunks}")
    assert total_chunks >= 40, f"Expected at least 40 chunks, got {total_chunks}"

    # Verify retrieval works without LLM
    hits = store.query("subscription credit facility", n_results=5)
    print(f"\nTop result for 'subscription credit facility':")
    print(f"  {hits[0].metadata.get('filename')} p{hits[0].metadata.get('page')} dist={hits[0].distance:.3f}")
    assert hits[0].distance < 0.75, "Expected a relevant result for a known corpus term"


# ---------------------------------------------------------------------------
# Full chat integration test — requires OpenAI API key
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_chat(tmp_path):
    """Ingest portal files and answer a sample question with GPT-4o."""
    from app.config import settings
    from app.crawler.portal_client import PortalClient
    from app.llm.openai_client import OpenAIClient

    client = PortalClient(api_base_url="https://fo1.api.altius.finance/api")
    token = await client.login(settings.portal_username, settings.portal_password)
    files = await client.list_files(token, 10495)

    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    llm = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    pipe = RAGPipeline(vector_store=store, llm_client=llm)

    # Ingest all files
    for file_meta in files:
        dest = tmp_path / f"{file_meta['id']}_{file_meta['name']}"
        await client.download_file(file_meta["file_url"], dest)
        try:
            await pipe.ingest(dest, {
                "file_id": file_meta["id"],
                "filename": file_meta["name"],
                "doc_type": file_meta.get("document_type", ""),
                "file_path": str(dest),
            })
        except ValueError:
            pass

    # Sample question from the assignment
    question = "How did the manager describe the use of the subscription credit facility across 2024?"
    response = await pipe.query(question)

    print(f"\nQ: {question}")
    print(f"A: {response.answer[:800]}")
    print(f"\nCitations ({len(response.citations)}):")
    for c in response.citations[:5]:
        print(f"  {c.filename} p{c.page} [{c.period}]")

    assert not response.is_out_of_corpus
    assert len(response.answer) > 50
    assert len(response.citations) >= 1
