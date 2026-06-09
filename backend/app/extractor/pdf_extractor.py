"""
PDFExtractor: pdfplumber (tables + text) → LLM → StatementData.

pdfplumber is better than PyMuPDF for table-heavy statements because it
preserves cell boundaries and column alignment.  We fall back to PyMuPDF
if pdfplumber cannot open the file (e.g. encrypted PDFs).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pdfplumber
import fitz  # PyMuPDF fallback

from app.llm.base import BaseLLMClient
from .base import BaseExtractor, StatementData


_SYSTEM_PROMPT = """\
You extract structured data from private equity capital account statements.
These documents have heterogeneous layouts — the field for the LP's current
stake value may be labelled: "Ending Capital Balance", "Closing NAV",
"Partner's Capital — Ending", "Capital Account Value", "Net Asset Value",
"Total Capital Account", "Ending Balance", or similar.

Return ONLY valid JSON with these fields:
{
  "fund_name": "<string or null>",
  "statement_date": "<YYYY-MM-DD or null>",
  "current_value": <number or null>,
  "confidence": <0.0–1.0>,
  "value_field_label": "<exact label used in doc for current_value, or null>",
  "notes": "<any warnings or ambiguities>"
}
If a field cannot be found, use null — never fabricate values.\
"""

_USER_TMPL = """\
Filename: {filename}

Extracted document content:
\"\"\"
{content}
\"\"\"

Extract the financial data.\
"""


def _extract_content(file_path: Path, max_chars: int = 6000) -> str:
    """
    Extract text + tables from a PDF.
    pdfplumber first; PyMuPDF if pdfplumber fails.
    """
    try:
        parts: list[str] = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                # Tables first — they carry the numeric data
                for table in page.extract_tables() or []:
                    for row in table:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        parts.append(" | ".join(cleaned))
                # Then plain text
                text = page.extract_text() or ""
                if text:
                    parts.append(text)
                if sum(len(p) for p in parts) >= max_chars:
                    break
        content = "\n".join(parts)
        if content.strip():
            return content[:max_chars]
    except Exception:
        pass

    # PyMuPDF fallback
    try:
        doc = fitz.open(str(file_path))
        text = "\n".join(page.get_text() for page in doc[:5])
        doc.close()
        return text[:max_chars]
    except Exception as exc:
        raise ValueError(f"Could not extract text from {file_path.name}: {exc}") from exc


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


class PDFExtractor(BaseExtractor):
    def __init__(self, llm_client: BaseLLMClient):
        self._llm = llm_client

    async def extract(self, file_path: Path) -> StatementData:
        content = _extract_content(file_path)
        if not content.strip():
            raise ValueError(f"No text could be extracted from {file_path.name}")

        raw = await self._llm.chat_json(
            system=_SYSTEM_PROMPT,
            user=_USER_TMPL.format(filename=file_path.name, content=content),
        )

        fund_name: str = raw.get("fund_name") or file_path.stem
        statement_date = _parse_date(raw.get("statement_date"))
        current_value = raw.get("current_value")
        if current_value is not None:
            try:
                current_value = float(current_value)
            except (TypeError, ValueError):
                current_value = None

        if statement_date is None:
            raise ValueError(
                f"Could not parse statement_date from LLM response for {file_path.name}: {raw}"
            )

        return StatementData(
            fund_name=fund_name,
            statement_date=statement_date,
            current_value=current_value,
            raw_fields=raw,
            confidence=float(raw.get("confidence", 0.5)),
            extraction_notes=raw.get("notes", ""),
        )
