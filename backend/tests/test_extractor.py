"""
Extractor tests.

Unit tests mock the LLM entirely.
A separate PDF-parsing test verifies pdfplumber can read real portal files
(no LLM key needed).
Integration test requires a real OpenAI key.
"""
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.llm.base import BaseLLMClient
from app.extractor import PDFExtractor, StatementData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(response: dict) -> BaseLLMClient:
    llm = MagicMock(spec=BaseLLMClient)
    llm.chat_json = AsyncMock(return_value=response)
    return llm


def _write_minimal_pdf(path: Path, content: str) -> None:
    """Write the smallest valid PDF that pdfplumber can open and read."""
    # We use PyMuPDF to create a real PDF with text so pdfplumber can parse it
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), content, fontsize=10)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_returns_statement_data(tmp_path):
    """Happy path: LLM returns all fields, StatementData is correct."""
    pdf = tmp_path / "statement.pdf"
    _write_minimal_pdf(pdf, "Fund Alpha LP  Ending Capital Balance: $1,250,000  Date: 2024-03-31")

    llm = _mock_llm({
        "fund_name": "Fund Alpha LP",
        "statement_date": "2024-03-31",
        "current_value": 1250000.0,
        "confidence": 0.97,
        "value_field_label": "Ending Capital Balance",
        "notes": "",
    })

    extractor = PDFExtractor(llm_client=llm)
    result = await extractor.extract(pdf)

    assert result.fund_name == "Fund Alpha LP"
    assert result.statement_date == date(2024, 3, 31)
    assert result.current_value == pytest.approx(1_250_000.0)
    assert result.confidence == pytest.approx(0.97)
    llm.chat_json.assert_called_once()


@pytest.mark.asyncio
async def test_extract_null_current_value_is_surfaced(tmp_path):
    """If current_value is null in LLM response, it propagates as None (not 0)."""
    pdf = tmp_path / "statement.pdf"
    _write_minimal_pdf(pdf, "Some fund statement text")

    llm = _mock_llm({
        "fund_name": "Fund Beta LP",
        "statement_date": "2024-06-30",
        "current_value": None,
        "confidence": 0.60,
        "value_field_label": None,
        "notes": "Could not locate ending balance field",
    })

    result = await PDFExtractor(llm).extract(pdf)
    assert result.current_value is None
    assert result.confidence == pytest.approx(0.60)
    assert "Could not locate" in result.extraction_notes


@pytest.mark.asyncio
async def test_extract_raises_on_missing_date(tmp_path):
    """Missing statement_date raises ValueError — never silently skipped."""
    pdf = tmp_path / "statement.pdf"
    _write_minimal_pdf(pdf, "Some content")

    llm = _mock_llm({
        "fund_name": "Fund Gamma LP",
        "statement_date": None,
        "current_value": 500000.0,
        "confidence": 0.4,
        "value_field_label": None,
        "notes": "Date not found",
    })

    with pytest.raises(ValueError, match="statement_date"):
        await PDFExtractor(llm).extract(pdf)


# ---------------------------------------------------------------------------
# PDF text extraction test — no LLM key required
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_pdfplumber_reads_real_portal_files(tmp_path):
    """
    Download 3 statement PDFs from the portal and verify pdfplumber can
    extract meaningful text from them (no LLM needed).
    Also reports what raw text/tables look like for the two error2 files.
    """
    from app.config import settings
    from app.crawler.portal_client import PortalClient
    from app.extractor.pdf_extractor import _extract_content

    client = PortalClient(api_base_url="https://fo1.api.altius.finance/api")
    token = await client.login(settings.portal_username, settings.portal_password)
    files = await client.list_files(token, 10495)

    # Pick first 3 statement files + the 2 error2 files
    statements = [f for f in files if (f.get("document_type") or "").lower() == "capital account"][:3]
    error2 = [f for f in files if f["name"] in ("7470-01-136 - 3 2021.pdf", "345.pdf")]
    targets = statements + error2

    for file_meta in targets:
        dest = tmp_path / f"{file_meta['id']}_{file_meta['name']}"
        await client.download_file(file_meta["file_url"], dest)
        try:
            content = _extract_content(dest)
            print(f"\n=== {file_meta['name']} ({len(content)} chars) ===")
            print(content[:600])
            assert len(content) > 50, f"Too little text extracted from {file_meta['name']!r}"
        except ValueError as exc:
            # error2 files may be unreadable — report but don't fail
            print(f"\n=== {file_meta['name']}: EXTRACTION FAILED: {exc} ===")


# ---------------------------------------------------------------------------
# Integration test — full LLM extraction on real files (needs API key)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_extract_statements(tmp_path):
    """Extract fund_name, statement_date, current_value from 3 real statements."""
    from app.config import settings
    from app.crawler.portal_client import PortalClient
    from app.llm.openai_client import OpenAIClient

    client = PortalClient(api_base_url="https://fo1.api.altius.finance/api")
    token = await client.login(settings.portal_username, settings.portal_password)
    files = await client.list_files(token, 10495)
    statements = [f for f in files if (f.get("document_type") or "").lower() == "capital account"][:3]

    llm = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    extractor = PDFExtractor(llm_client=llm)

    for file_meta in statements:
        dest = tmp_path / f"{file_meta['id']}_{file_meta['name']}"
        await client.download_file(file_meta["file_url"], dest)
        result = await extractor.extract(dest)
        print(f"\n  {file_meta['name']}")
        print(f"    fund_name:      {result.fund_name!r}")
        print(f"    statement_date: {result.statement_date}")
        print(f"    current_value:  {result.current_value:,.2f}" if result.current_value else "    current_value:  None")
        print(f"    confidence:     {result.confidence:.2f}")
        print(f"    notes:          {result.extraction_notes!r}")

        assert result.fund_name, "fund_name must not be empty"
        assert result.statement_date is not None
