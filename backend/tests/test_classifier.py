"""
Classifier tests.

Unit tests cover heuristic routing and LLM gating.
Integration test downloads a handful of real portal files and classifies them.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.models.file_record import FileType
from app.classifier import HybridClassifier, ClassificationResult
from app.llm.base import BaseLLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def classify(filename: str, portal_type: str | None = None, llm=None) -> ClassificationResult:
    clf = HybridClassifier(llm_client=llm)
    return await clf.classify(Path("/nonexistent.pdf"), filename, portal_type)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_portal_label_takes_priority():
    """Portal 'Capital account' label wins over any filename signal."""
    result = await classify("random_file.pdf", portal_type="Capital account")
    assert result.file_type == FileType.CAPITAL_STATEMENT
    assert result.method == "portal"
    assert result.confidence >= 0.90


@pytest.mark.asyncio
async def test_heuristic_detects_statements():
    """Known statement filenames are classified without LLM."""
    names = [
        "fund_beta_capacct_q3_2025.pdf",
        "fund_alpha_Q3_2025_CapitalAccount.pdf",
        "fund_zeta - Capital Statement - 2025-09-30.pdf",
        "fund_delta_CAS_Jun2025.pdf",
        "fund_gamma_CAS_Sep2025.pdf",
    ]
    for name in names:
        result = await classify(name)
        assert result.file_type == FileType.CAPITAL_STATEMENT, f"Failed for {name!r}"
        assert result.method == "heuristic"


@pytest.mark.asyncio
async def test_heuristic_detects_reports():
    """Known report filenames are classified without LLM."""
    names = [
        "fund_alpha_Q3_2021_Update.pdf",
        "fund_zeta_2023-03-31_fs_commentary.pdf",
        "fund_epsilon_letter_q3_2025.pdf",
        "fund_gamma - Quarterly Update - 2022-06-30.pdf",
        "fund_beta_FS_Commentary_Dec2024.pdf",
    ]
    for name in names:
        result = await classify(name)
        assert result.file_type == FileType.REPORT, f"Failed for {name!r}"
        assert result.method == "heuristic"


@pytest.mark.asyncio
async def test_llm_called_for_ambiguous_file(tmp_path):
    """A filename with no pattern match triggers the LLM."""
    # Write a dummy PDF-like file
    dummy = tmp_path / "345.pdf"
    dummy.write_bytes(b"%PDF-1.4 dummy content capital account something")

    mock_llm = MagicMock(spec=BaseLLMClient)
    mock_llm.chat_json = AsyncMock(return_value={
        "file_type": "report",
        "confidence": 0.75,
        "reasoning": "Narrative content detected",
    })

    clf = HybridClassifier(llm_client=mock_llm)
    result = await clf.classify(dummy, "345.pdf", portal_document_type=None)

    assert result.method == "llm"
    assert result.file_type == FileType.REPORT
    mock_llm.chat_json.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_when_no_llm_and_no_match():
    """Without LLM, an unrecognised file returns UNKNOWN rather than a guess."""
    result = await classify("7470-01-136 - 3 2021.pdf", llm=None)
    assert result.file_type == FileType.UNKNOWN
    assert result.is_uncertain is True


# ---------------------------------------------------------------------------
# Integration test — classifies real downloaded files
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_classify_portal_files(tmp_path):
    """
    Downloads a representative sample of portal files and classifies them.
    Verifies statements → CAPITAL_STATEMENT, reports → REPORT.
    Also reports what happens with the two 'error2' files.
    """
    import httpx
    from app.config import settings
    from app.crawler.portal_client import PortalClient
    from app.llm.openai_client import OpenAIClient

    client = PortalClient(api_base_url="https://fo1.api.altius.finance/api")
    token = await client.login(settings.portal_username, settings.portal_password)
    files = await client.list_files(token, 10495)

    llm = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    clf = HybridClassifier(llm_client=llm)

    results = {}
    # Download and classify all 40 files
    for file_meta in files:
        fid = file_meta["id"]
        fname = file_meta["name"]
        ptype = file_meta.get("document_type")
        dest = tmp_path / f"{fid}_{fname}"
        await client.download_file(file_meta["file_url"], dest)
        result = await clf.classify(dest, fname, portal_document_type=ptype)
        results[fname] = result
        print(f"  [{result.method:10s}] [{result.file_type.value:20s}] conf={result.confidence:.2f}  {fname}")

    # Known statements (portal labels them "Capital account")
    statement_files = [f for f, r in results.items() if r.file_type == FileType.CAPITAL_STATEMENT]
    report_files = [f for f, r in results.items() if r.file_type == FileType.REPORT]
    unknown_files = [f for f, r in results.items() if r.file_type == FileType.UNKNOWN]

    print(f"\nStatements: {len(statement_files)}")
    print(f"Reports:    {len(report_files)}")
    print(f"Unknown:    {len(unknown_files)}: {unknown_files}")

    # Sanity checks based on known portal content
    assert len(statement_files) >= 6, "Expected at least 6 capital statements"
    assert len(report_files) >= 10, "Expected at least 10 reports"

    # Report on the two error2 files explicitly
    error2_files = [f for f in results if f in ("7470-01-136 - 3 2021.pdf", "345.pdf")]
    print(f"\n=== error2 files ===")
    for f in error2_files:
        r = results[f]
        print(f"  {f}: type={r.file_type.value}, confidence={r.confidence:.2f}, method={r.method}, reasoning={r.reasoning!r}")
