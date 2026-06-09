"""
HybridClassifier: portal label → filename heuristics → LLM fallback.

Priority order keeps LLM costs near zero for the common case while
ensuring genuinely ambiguous files get a real answer (not a silent guess).
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF — fast text extraction for the LLM sample

from app.llm.base import BaseLLMClient
from app.models.file_record import FileType
from .base import BaseClassifier, ClassificationResult


# ---------------------------------------------------------------------------
# Patterns (case-insensitive, applied to the sanitised filename)
# ---------------------------------------------------------------------------

_STATEMENT_RE = re.compile(
    r"capital.{0,10}(account|statement|acct|acc)"
    r"|cap.{0,5}acct"
    r"|capacct"
    r"|(?<![A-Za-z])cas(?![A-Za-z])"   # _CAS_ / .CAS. but not "because"
    r"|capital_account",
    re.IGNORECASE,
)

_REPORT_RE = re.compile(
    r"(quarterly.{0,5}update|q[1-4].{0,4}update|q[1-4].{0,4}letter)"
    r"|(fs.{0,5}commentary|fund.{0,5}commentary)"
    r"|(?<![A-Za-z])(quarterly|report|update|letter|commentary)(?![A-Za-z])",
    re.IGNORECASE,
)

# Portal API document_type values → FileType
_PORTAL_MAP: dict[str, FileType] = {
    "capital account": FileType.CAPITAL_STATEMENT,
    "report": FileType.REPORT,
}

_LLM_SYSTEM = """You are a financial document classifier for a private equity family office.
Classify the document into exactly one of:
- capital_statement  (capital account statement, partner capital statement, NAV statement — tabular position data for one LP)
- report             (quarterly update, letter, commentary, narrative fund report)
- other              (tax forms, capital call notices, side letters, marketing decks, etc.)

Respond with JSON: {"file_type": "<label>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}"""

_LLM_USER_TMPL = """Filename: {filename}

First {chars} characters of document text:
\"\"\"
{text}
\"\"\"

Classify this document."""


def _extract_text_sample(file_path: Path, max_chars: int = 1200) -> str:
    try:
        doc = fitz.open(str(file_path))
        text = ""
        for page in doc[:3]:
            text += page.get_text()
            if len(text) >= max_chars:
                break
        doc.close()
        return text[:max_chars].strip()
    except Exception:
        return ""


_LLM_TYPE_MAP = {
    "capital_statement": FileType.CAPITAL_STATEMENT,
    "report": FileType.REPORT,
    "other": FileType.OTHER,
}


class HybridClassifier(BaseClassifier):
    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        confidence_threshold: float = 0.70,
    ):
        self._llm = llm_client
        self._threshold = confidence_threshold

    async def classify(
        self,
        file_path: Path,
        filename: str,
        portal_document_type: str | None = None,
    ) -> ClassificationResult:

        # 1. Trust the portal's own label (it's already human-verified)
        if portal_document_type:
            for key, ftype in _PORTAL_MAP.items():
                if key in portal_document_type.lower():
                    return ClassificationResult(
                        file_type=ftype,
                        confidence=0.95,
                        method="portal",
                        reasoning=f"portal label: {portal_document_type!r}",
                    )

        # 2. Filename heuristics
        if _STATEMENT_RE.search(filename):
            return ClassificationResult(
                file_type=FileType.CAPITAL_STATEMENT,
                confidence=0.85,
                method="heuristic",
                reasoning=f"filename matched statement pattern",
            )
        if _REPORT_RE.search(filename):
            return ClassificationResult(
                file_type=FileType.REPORT,
                confidence=0.85,
                method="heuristic",
                reasoning=f"filename matched report pattern",
            )

        # 3. LLM fallback for ambiguous filenames
        if self._llm and file_path.exists():
            text_sample = _extract_text_sample(file_path)
            try:
                raw = await self._llm.chat_json(
                    system=_LLM_SYSTEM,
                    user=_LLM_USER_TMPL.format(
                        filename=filename,
                        chars=len(text_sample),
                        text=text_sample,
                    ),
                )
                ftype = _LLM_TYPE_MAP.get(raw.get("file_type", ""), FileType.OTHER)
                confidence = float(raw.get("confidence", 0.5))
                return ClassificationResult(
                    file_type=ftype,
                    confidence=confidence,
                    method="llm",
                    reasoning=raw.get("reasoning", ""),
                )
            except Exception as exc:
                return ClassificationResult(
                    file_type=FileType.UNKNOWN,
                    confidence=0.0,
                    method="none",
                    reasoning=f"LLM error: {exc}",
                )

        # 4. Genuinely unknown — surface it, never silently bucket
        return ClassificationResult(
            file_type=FileType.UNKNOWN,
            confidence=0.0,
            method="none",
            reasoning="No heuristic matched and no LLM configured",
        )
